import unittest, os, shutil, json, tempfile, uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, Mock
import grpc

from protos import blog_pb2
from consensus import RaftLogEntry
from server import Server, SUCCESS

def _mk_test_dirs():
    root = tempfile.mkdtemp()
    logs = os.path.join(root, "replica_logs")
    os.makedirs(logs, exist_ok=True)
    return root, logs

def _mk_replica_cfg(root):
    logs = os.path.join(root, "replica_logs")
    cfg = {
        "id": "test_replica",
        "host": "localhost",
        "port": 50051,
        "raft_store": os.path.join(logs, "raft.json"),
        "posts_store": os.path.join(logs, "posts.csv"),
        "users_store": os.path.join(logs, "users.csv"),
        "writers_store": os.path.join(logs, "writers.csv"),
        "comments_store": os.path.join(logs, "comments.csv"),
    }

    # raft state
    with open(cfg["raft_store"], "w") as f:
        json.dump({"currentTerm": 0, "votedFor": None, "log": []}, f)

    # csv headers
    with open(cfg["posts_store"], "w") as f:
        f.write("post_id,author,title,content,timestamp,likes\n")
    with open(cfg["users_store"], "w") as f:
        f.write("email\n")
    with open(cfg["writers_store"], "w") as f:
        f.write("email,name,password\n")
    with open(cfg["comments_store"], "w") as f:
        f.write("post_id,email,text,timestamp\n")

    replicas_meta = {"replicas": [{"id": "replica1", "host": "localhost", "port": 50052}]}
    replicas_path = os.path.join(root, "replicas.json")
    with open(replicas_path, "w") as f:
        json.dump(replicas_meta, f)

    return cfg, replicas_meta

class _MockBlogStub:
    def __init__(self):
        self.RequestVote = MagicMock(return_value=blog_pb2.Response(term=1, voteGranted=True))
        self.AppendEntries = MagicMock(return_value=blog_pb2.Response(term=1, success=True))
        self.RPCGetLeaderInfo = MagicMock(
            return_value=blog_pb2.Response(operation=blog_pb2.SUCCESS, info=["replica1"])
        )
        self._channel = MagicMock()
        self._channel.check_connectivity_state.return_value = grpc.ChannelConnectivity.READY

class TestServer(unittest.TestCase):
    def setUp(self):
        self.root, self.logdir = _mk_test_dirs()
        self.replica_cfg, self.replicas_meta = _mk_replica_cfg(self.root)

        self.p_timer     = patch("server.threading.Timer")
        self.p_email     = patch("server.email_worker")
        self.p_blogstub  = patch("server.blog_pb2_grpc.BlogStub", return_value=_MockBlogStub())
        self.p_buildstub = patch("server.build_stub", return_value=_MockBlogStub())
        self.p_replicas  = patch("server.get_replicas_config", return_value=self.replicas_meta["replicas"])

        self.mock_timer     = self.p_timer.start()
        self.mock_email     = self.p_email.start()
        self.mock_blogstub  = self.p_blogstub.start()
        self.mock_buildstub = self.p_buildstub.start()
        self.mock_replicas  = self.p_replicas.start()

        for p in (self.p_timer, self.p_email, self.p_blogstub, self.p_buildstub, self.p_replicas):
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_init(self):
        srv = Server(self.replica_cfg)
        self.assertEqual(srv.replica_id, "test_replica")
        self.assertTrue(self.mock_timer.called)
        srv.stop()

    def test_get_cluster_stubs(self):
        srv = Server(self.replica_cfg)
        stubs = srv.get_cluster_stubs()
        self.assertIn("replica1", stubs)
        self.assertIsInstance(stubs["replica1"], _MockBlogStub)
        srv.stop()

    def test_reset_election_timer(self):
        timer_inst = MagicMock()
        self.mock_timer.return_value = timer_inst
        srv = Server(self.replica_cfg)
        self.mock_timer.reset_mock()
        srv.reset_election_timer()
        timer_inst.cancel.assert_called_once()
        timer_inst.start.assert_called_once()
        srv.stop()

    def test_become_candidate(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role, srv.raft_node.currentTerm = "follower", 0
        srv.become_candidate()
        self.assertEqual(srv.raft_node.role, "leader")
        self.assertEqual(srv.raft_node.currentTerm, 1)
        self.assertEqual(srv.raft_node.votedFor, "test_replica")
        srv.stop()

    def test_become_leader(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "candidate"
        srv.become_leader()
        self.assertEqual(srv.raft_node.role, "leader")
        self.assertIn("replica1", srv.raft_node.nextIndex)
        self.assertIn("replica1", srv.raft_node.matchIndex)
        srv.stop()

    def test_leader_heartbeat(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.check_leader_status = MagicMock()
        srv.send_append_entries_to_all = MagicMock()
        srv.reset_heartbeat_timer = MagicMock()
        srv.leader_heartbeat()
        srv.check_leader_status.assert_called_once()
        srv.send_append_entries_to_all.assert_called_once()
        srv.reset_heartbeat_timer.assert_called_once()
        srv.stop()

    def test_replicate_command(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        start_len = len(srv.raft_node.log)
        res = srv.replicate_command("SUBSCRIBE", ["test@example.com"])
        self.assertEqual(res, SUCCESS)
        self.assertEqual(len(srv.raft_node.log), start_len + 1)
        self.assertEqual(srv.raft_node.log[-1].operation, "SUBSCRIBE")
        srv.stop()

    def test_apply_committed_entries(self):
        srv = Server(self.replica_cfg)
        srv.apply_blog_operation, srv.save_data = MagicMock(), MagicMock()
        srv.raft_node.log = [
            RaftLogEntry(term=1, operation="SUBSCRIBE", params=["x"]),
            RaftLogEntry(term=1, operation="CREATE_ACCOUNT", params=["n", "x", "p"]),
        ]
        srv.raft_node.commitIndex, srv.raft_node.lastApplied = 2, 0
        srv.apply_committed_entries()
        self.assertEqual(srv.apply_blog_operation.call_count, 2)
        self.assertEqual(srv.raft_node.lastApplied, 2)
        srv.save_data.assert_called_once()
        srv.stop()

    def test_apply_blog_operation_subscribe(self):
        srv = Server(self.replica_cfg)
        entry = RaftLogEntry(term=1, operation="SUBSCRIBE", params=["test@example.com"])
        srv.apply_blog_operation(entry)
        self.assertIn("test@example.com", srv.user_database)
        srv.stop()

    def test_apply_blog_operation_create_account(self):
        srv = Server(self.replica_cfg)
        entry = RaftLogEntry(term=1, operation="CREATE_ACCOUNT",
                             params=["Test User", "test@example.com", "pw"])
        srv.apply_blog_operation(entry)
        self.assertIn("test@example.com", srv.writers_database)
        self.assertEqual(srv.writers_database["test@example.com"].name, "Test User")
        srv.stop()

    def test_apply_blog_operation_create_post(self):
        srv = Server(self.replica_cfg)
        srv.user_database["author@example.com"] = MagicMock()
        post_id, ts = str(uuid.uuid4()), datetime.now().isoformat()
        entry = RaftLogEntry(term=1, operation="CREATE_POST",
                             params=[post_id, "t", "c", "author@example.com", ts])
        srv.apply_blog_operation(entry)
        self.assertIn(post_id, srv.posts_database)
        self.assertEqual(srv.posts_database[post_id].title, "t")
        srv.stop()

    def test_apply_blog_operation_comment_post(self):
        srv = Server(self.replica_cfg)
        post_id = str(uuid.uuid4())
        srv.posts_database[post_id] = MagicMock(comments=[])
        entry = RaftLogEntry(term=1, operation="COMMENT_POST",
                             params=[post_id, "u@example.com", "hey"])
        srv.apply_blog_operation(entry)
        self.assertEqual(len(srv.posts_database[post_id].comments), 1)
        self.assertEqual(srv.posts_database[post_id].comments[0].text, "hey")
        srv.stop()

    def test_apply_blog_operation_like_unlike(self):
        srv = Server(self.replica_cfg)
        post_id = str(uuid.uuid4())
        srv.posts_database[post_id] = MagicMock(like=MagicMock(), unlike=MagicMock())
        srv.user_database["u@example.com"] = MagicMock()
        like_entry = RaftLogEntry(term=1, operation="LIKE_POST", params=[post_id, "u@example.com"])
        srv.apply_blog_operation(like_entry)
        srv.posts_database[post_id].like.assert_called_once()
        unlike_entry = RaftLogEntry(term=1, operation="UNLIKE_POST", params=[post_id, "u@example.com"])
        srv.apply_blog_operation(unlike_entry)
        srv.posts_database[post_id].unlike.assert_called_once()
        srv.stop()

    def test_apply_blog_operation_delete_post(self):
        srv = Server(self.replica_cfg)
        post_id, author = str(uuid.uuid4()), "a@example.com"
        srv.posts_database[post_id] = MagicMock(author=author)
        srv.user_database[author] = MagicMock(posts=[post_id])
        entry = RaftLogEntry(term=1, operation="DELETE_POST", params=[post_id, author])
        srv.apply_blog_operation(entry)
        self.assertNotIn(post_id, srv.posts_database)
        srv.stop()

    def test_request_vote_rpc(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.currentTerm, srv.raft_node.votedFor = 1, None
        req = blog_pb2.Request(term=2, candidateId="replica1", lastLogIndex=0, lastLogTerm=0)
        resp = srv.RequestVote(req, None)
        self.assertTrue(resp.voteGranted)
        self.assertEqual(srv.raft_node.currentTerm, 2)
        self.assertEqual(srv.raft_node.votedFor, "replica1")
        srv.stop()

    def test_append_entries_rpc(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.currentTerm = 1
        srv.apply_committed_entries = MagicMock()
        req = blog_pb2.Request(term=1, leaderId="replica1", prevLogIndex=0, prevLogTerm=0,
                               leaderCommit=1, entries=[blog_pb2.RaftLogEntry(term=1, operation="SUBSCRIBE", params=["x"])])
        resp = srv.AppendEntries(req, None)
        self.assertTrue(resp.success)
        self.assertEqual(len(srv.raft_node.log), 1)
        srv.apply_committed_entries.assert_called_once()
        srv.stop()

    def test_rpc_create_post(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        srv.notify_followers_of_new_post = MagicMock()
        req = blog_pb2.Request(info=["t", "c", "a@example.com"])
        resp = srv.RPCCreatePost(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.notify_followers_of_new_post.assert_called_once()
        srv.stop()

    def test_rpc_login(self):
        srv = Server(self.replica_cfg)
        from writer import Writer
        w = Mock(spec=Writer); w.verify_password = MagicMock(return_value=True)
        srv.writers_database["x@gmail.com"] = w
        req = blog_pb2.Request(info=["x@gmail.com", "qwertyuiop"])
        resp = srv.RPCLogin(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        w.verify_password.assert_called_once_with("qwertyuiop")
        srv.stop()

    def test_rpc_create_account(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        req = blog_pb2.Request(info=["u", "x@gmail.com", "qwertyuiop"])
        resp = srv.RPCCreateAccount(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("CREATE_ACCOUNT", ["u", "x@gmail.com", "qwertyuiop"])
        srv.stop()

    def test_rpc_comment_post(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        post_id = str(uuid.uuid4())
        srv.posts_database[post_id] = MagicMock()
        srv.user_database["u@example.com"] = MagicMock()
        req = blog_pb2.Request(info=[post_id, "u@example.com", "cmt"])
        resp = srv.RPCCommentPost(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("COMMENT_POST", [post_id, "u@example.com", "cmt"])
        srv.stop()

    def test_rpc_get_all_posts(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"

        post1 = MagicMock()
        post2 = MagicMock()

        post1_msg = blog_pb2.Post(post_id="post1", author="author1", title="title1", content="content1", timestamp="ts1", likes=[])
        post2_msg = blog_pb2.Post(post_id="post2", author="author2", title="title2", content="content2", timestamp="ts2", likes=[])

        post1.to_proto.return_value = post1_msg
        post2.to_proto.return_value = post2_msg

        srv.posts_database = {
            "p1": post1,
            "p2": post2
        }

        req = blog_pb2.Request()
        resp = srv.RPCGetAllPosts(req, None)

        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        self.assertEqual(len(resp.posts), 2)
        self.assertEqual(resp.posts[0].post_id, "post1")
        self.assertEqual(resp.posts[1].post_id, "post2")

        srv.stop()

    def test_rpc_subscribe(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        req = blog_pb2.Request(info=["testgmail@gmail.com"])
        resp = srv.RPCSubscribe(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("SUBSCRIBE", ["testgmail@gmail.com"])
        srv.stop()

    def test_rpc_logout(self):
        srv = Server(self.replica_cfg)
        srv.writers_database["x@example.com"] = MagicMock()
        req = blog_pb2.Request(info=["x@example.com"])
        resp = srv.RPCLogout(req, None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.stop()

    def test_rpc_search_users(self):
        srv = Server(self.replica_cfg)
        srv.user_database["u@example.com"] = MagicMock()
        resp = srv.RPCSearchUsers(blog_pb2.Request(info=["u@example.com"]), None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        self.assertEqual(resp.info[0], "u@example.com")
        srv.stop()

    def test_rpc_delete_account(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        srv.user_database["u@example.com"] = MagicMock()
        resp = srv.RPCDeleteAccount(blog_pb2.Request(info=["u@example.com"]), None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("DELETE_ACCOUNT", ["u@example.com"])
        srv.stop()

    def test_rpc_add_replica(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        replica_cfg = json.dumps({"id": "replica2", "host": "localhost", "port": 50053})
        resp = srv.RPCAddReplica(blog_pb2.Request(info=[replica_cfg]), None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("ADD_REPLICA", [replica_cfg])
        srv.stop()

    def test_rpc_remove_replica(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        srv.replicate_command = MagicMock(return_value=SUCCESS)
        resp = srv.RPCRemoveReplica(blog_pb2.Request(info=["replica1"]), None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        srv.replicate_command.assert_called_once_with("REMOVE_REPLICA", ["replica1"])
        srv.stop()

    def test_rpc_get_leader_info(self):
        srv = Server(self.replica_cfg)
        srv.raft_node.role = "leader"
        resp = srv.RPCGetLeaderInfo(blog_pb2.Request(), None)
        self.assertEqual(resp.operation, blog_pb2.SUCCESS)
        self.assertEqual(resp.info[0], "test_replica")
        srv.stop()

if __name__ == "__main__":
    unittest.main()
