import csv
import os
import random
import time
import threading
import grpc
import json
import logging
from concurrent import futures
from datetime import datetime
import uuid
from email_validator import validate_email, EmailNotValidError

from protos import blog_pb2, blog_pb2_grpc
from user import User
from post import Post
from comment import Comment
from util import hash_password
from consensus import (
    RaftNode,
    build_stub,
    get_replicas_config,
    RaftLogEntry
)
from writer import Writer

SUCCESS = 0
FAILURE = 1

def find_leader_stub():
    """Find the current leader and return a gRPC stub to communicate with it"""
    replicas = get_replicas_config()
    for r in replicas:
        try:
            channel = grpc.insecure_channel(f"{r['host']}:{r['port']}")
            stub = blog_pb2_grpc.BlogStub(channel)
            resp = stub.RPCGetLeaderInfo(blog_pb2.Request(), timeout=2.0)
            if resp.operation == blog_pb2.SUCCESS and resp.info:
                leader_id = resp.info[0]
                leader_cfg = next((cfg for cfg in replicas if cfg["id"] == leader_id), None)
                if leader_cfg:
                    leader_channel = grpc.insecure_channel(f"{leader_cfg['host']}:{leader_cfg['port']}")
                    return blog_pb2_grpc.BlogStub(leader_channel)
        except Exception as e:
            print("Failed to contact replica:", r, "Error:", e)
            continue
    return None

class Server(blog_pb2_grpc.BlogServicer):
    ELECTION_TIMEOUT = random.uniform(3.0, 5.0)
    HEARTBEAT_INTERVAL = 1.5

    def __init__(self, replica_config):
        self.replica_id = replica_config["id"]
        self.host = replica_config["host"]
        self.port = replica_config["port"]
        self.raft_store = replica_config["raft_store"]
        self.posts_store = replica_config["posts_store"]
        self.users_store = replica_config["users_store"]
        self.writers_store = replica_config["writers_store"]
        self.comments_store = replica_config["comments_store"]
        # self.subscriptions_store = replica_config["subscriptions_store"]

        # Blog data
        self.user_database = {}
        self.posts_database = {}  # post_id -> Post
        self.writers_database = {}  # email -> Writer

        # Build Raft
        self.raft_node = RaftNode(self.replica_id, self.raft_store)

        self._stubs_cache = {}
        self.replicas_config = get_replicas_config()
        for r in self.replicas_config:
            rid = r["id"]
            if rid != self.replica_id:
                self.raft_node.nextIndex[rid] = len(self.raft_node.log) + 1
                self.raft_node.matchIndex[rid] = 0

        # Load data
        self.load_data()
        self.raft_node.lastApplied = self.raft_node.commitIndex
        
        # Reset votedFor to break deadlock
        self.raft_node.votedFor = None
        self.raft_node.save_raft_state()
        
        # Start background
        self.stop_flag = False
        self.election_timer = None
        self.heartbeat_timer = None
        self.reset_election_timer()

    def get_cluster_stubs(self):
        # Refresh stubs for replicas that might have restarted
        for cfg in self.replicas_config:
            rid = cfg["id"]
            if rid != self.replica_id:
                # Check if we need to refresh this connection
                need_refresh = False
            
                if rid not in self._stubs_cache:
                    need_refresh = True
                else:
                    # Try a lightweight health check
                    try:
                        # Quick non-blocking check using gRPC channel state
                        channel = self._stubs_cache[rid]._channel
                        if channel.check_connectivity_state(True) in (
                            grpc.ChannelConnectivity.TRANSIENT_FAILURE,
                            grpc.ChannelConnectivity.SHUTDOWN
                        ):
                            need_refresh = True
                    except:
                        need_refresh = True
                
                if need_refresh:
                    try:
                        # Create a fresh connection with a short timeout
                        channel = grpc.insecure_channel(
                            f"{cfg['host']}:{cfg['port']}",
                            options=[
                                ('grpc.enable_retries', 0),
                                ('grpc.keepalive_time_ms', 5000),
                                ('grpc.keepalive_timeout_ms', 1000)
                            ]
                        )
                        self._stubs_cache[rid] = blog_pb2_grpc.BlogStub(channel)
                        logging.info(f"Refreshed connection to replica {rid}")
                    except Exception as e:
                        logging.error(f"Failed to refresh connection to replica {rid}: {e}")
        
        return self._stubs_cache

    def reset_election_timer(self):
        # cancel any existing timer
        if self.election_timer:
            self.election_timer.cancel()

        # pick a uniform random timeout between 3 and 5 seconds
        timeout = random.uniform(3.0, 5.0)
        self.ELECTION_TIMEOUT = timeout
        logging.info(f"Election timeout set to {timeout:.2f}s")

        # when it fires, try to become candidate
        self.election_timer = threading.Timer(timeout, self.become_candidate)
        self.election_timer.start()

    def reset_heartbeat_timer(self):
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
        self.heartbeat_timer = threading.Timer(self.HEARTBEAT_INTERVAL, self.leader_heartbeat)
        self.heartbeat_timer.start()

    def stop(self):
        self.stop_flag = True
        if self.election_timer:
            self.election_timer.cancel()
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

    # --------------------------------------------------------------------------
    # Raft roles - unchanged from original implementation
    # --------------------------------------------------------------------------
    def become_candidate(self):
        if self.raft_node.role == "leader":
            return
        self.raft_node.role = "candidate"
        self.raft_node.currentTerm += 1
        self.raft_node.votedFor = self.replica_id
        self.raft_node.save_raft_state()

        votes_granted = 1
        cluster_stubs = self.get_cluster_stubs()
        self.reset_election_timer()

        def request_vote_async(stub):
            try:
                req = blog_pb2.Request(
                    term=self.raft_node.currentTerm,
                    candidateId=self.replica_id,
                    lastLogIndex=self.raft_node.last_log_index(),
                    lastLogTerm=self.raft_node.last_log_term()
                )
                return stub.RequestVote(req, timeout=2.0)
            except:
                return None

        threads = []
        results = []
        for rid, stub in cluster_stubs.items():
            t = threading.Thread(target=lambda stub=stub: results.append(request_vote_async(stub)))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        currentTerm = self.raft_node.currentTerm
        for r in results:
            if not r:
                continue
            if r.term > currentTerm:
                self.raft_node.role = "follower"
                self.raft_node.currentTerm = r.term
                self.raft_node.votedFor = None
                self.raft_node.save_raft_state()
                return
            if r.voteGranted:
                votes_granted += 1

        majority = (len(self.replicas_config)//2)+1
        if votes_granted >= majority:
            self.become_leader()
        
        else:
            self.reset_election_timer()

    def become_leader(self):
        self.raft_node.role = "leader"
        for r in self.replicas_config:
            rid = r["id"]
            if rid != self.replica_id:
                self.raft_node.nextIndex[rid] = len(self.raft_node.log) + 1
                self.raft_node.matchIndex[rid] = 0
        self.reset_heartbeat_timer()

    def leader_heartbeat(self):
        if self.raft_node.role != "leader":
            return

        self.check_leader_status()
        if self.raft_node.role == "leader":
            self.send_append_entries_to_all()
            self.reset_heartbeat_timer()
         
    def check_leader_status(self):
        if self.raft_node.role != "leader":
            return

        # Count ourselves
        reachable = 1

    # Get fresh stubs for all followers
        stubs = self.get_cluster_stubs()

        # Build an empty AppendEntries (heartbeat) request
        hb_req = blog_pb2.Request(
            term=self.raft_node.currentTerm,
            leaderId=self.replica_id,
            prevLogIndex=self.raft_node.last_log_index(),
            prevLogTerm=self.raft_node.last_log_term(),
            leaderCommit=self.raft_node.commitIndex,
            entries=[],
        )

        # Ping each follower
        for rid, stub in stubs.items():
            try:
                resp = stub.AppendEntries(hb_req, timeout=0.5)
                # If they recognize our term, they’re alive
                if resp.term == self.raft_node.currentTerm:
                    reachable += 1
            except Exception:
                # RPC failed or stub unreachable → skip
                pass

        # Demote if we’ve lost majority
        majority = (len(self.replicas_config) // 2) + 1
        if reachable < majority:
            logging.warn(f"Leader stepping down: only {reachable}/{len(self.replicas_config)} live")
            self.raft_node.role = "follower"
        self.reset_election_timer()


    def send_append_entries_to_all(self):
        cstubs = self.get_cluster_stubs()
        term = self.raft_node.currentTerm
        
        # Use a thread pool to send AppendEntries in parallel
        threads = []
        for rid, stub in cstubs.items():
            nxt = self.raft_node.nextIndex[rid]
            prevLogIndex = nxt - 1
            prevLogTerm = 0
            if prevLogIndex > 0 and prevLogIndex <= len(self.raft_node.log):
                prevLogTerm = self.raft_node.log[prevLogIndex-1].term
            entries = []
            if nxt <= len(self.raft_node.log):
                for e in self.raft_node.log[nxt-1:]:
                    entries.append(
                        blog_pb2.RaftLogEntry(term=e.term, operation=e.operation, params=e.params)
                    )
            req = blog_pb2.Request(
                term=term,
                leaderId=self.replica_id,
                prevLogIndex=prevLogIndex,
                prevLogTerm=prevLogTerm,
                leaderCommit=self.raft_node.commitIndex,
                entries=entries
            )
            t = threading.Thread(target=self.append_entries_async, args=(stub, req, rid))
            t.start()
            threads.append(t)
        
        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=1.0)  # Add timeout to prevent blocking indefinitely

    def append_entries_async(self, stub, req, followerId):
        try:
            resp = stub.AppendEntries(req, timeout=2.0)
        except Exception as e:
            logging.error(f"AppendEntries RPC to {followerId} failed: {e}")
            return
        self.handle_append_entries_response(resp, followerId, req)


    def handle_append_entries_response(self, resp, followerId, req):
        if not resp:
            return
        if resp.term > self.raft_node.currentTerm:
            self.raft_node.role = "follower"
            self.raft_node.currentTerm = resp.term
            self.raft_node.votedFor = None
            self.raft_node.save_raft_state()
            return
        if self.raft_node.role != "leader":
            return
        if resp.success:
            appended_count = len(req.entries)
            if appended_count > 0:
                self.raft_node.nextIndex[followerId] += appended_count
                self.raft_node.matchIndex[followerId] = self.raft_node.nextIndex[followerId] - 1
            
            # Update commitIndex based on matchIndex values
            for n in range(self.raft_node.commitIndex + 1, len(self.raft_node.log) + 1):
                # Only consider entries from current term
                if n > 0 and self.raft_node.log[n-1].term == self.raft_node.currentTerm:
                    count = 1  # Count ourselves
                    for rid in self.raft_node.matchIndex:
                        if self.raft_node.matchIndex[rid] >= n:
                            count += 1
                    if count >= ((len(self.replicas_config)//2) + 1):
                        self.raft_node.commitIndex = n
                        break
            self.apply_committed_entries()
        else:
            # On failure, decrement nextIndex and retry
            if self.raft_node.nextIndex[followerId] > 1:
                self.raft_node.nextIndex[followerId] -= 1
            # Don't reset to 1 immediately - backtrack gradually
            return

    def apply_committed_entries(self):
        while self.raft_node.lastApplied<self.raft_node.commitIndex:
            self.raft_node.lastApplied += 1
            entry = self.raft_node.log[self.raft_node.lastApplied-1]
            self.apply_blog_operation(entry)
        self.save_data()

    # --------------------------------------------------------------------------
    # Data Loading and Saving
    # --------------------------------------------------------------------------
    def load_data(self):
        # Load users
        if os.path.exists(self.users_store):
            try:
                with open(self.users_store, "r") as f:
                    rd = csv.reader(f)
                    next(rd)  # Skip header
                    for row in rd:
                        email = row[0]
                        self.user_database[email] = User(email)
            except Exception as e:
                logging.error(f"Error loading users: {e}")

        # Load writers
        if os.path.exists(self.writers_store):
            try:
                with open(self.writers_store, "r") as f:
                    rd = csv.reader(f)
                    next(rd)  # Skip header
                    for row in rd:
                        email, name, hashed_password = row
                        self.writers_database[email] = Writer(email=email, name=name, hashed_password=hashed_password)
            except Exception as e:
                logging.error(f"Error loading writers: {e}")

        # Load posts
        if os.path.exists(self.posts_store):
            try:
                with open(self.posts_store, "r") as f:
                    rd = csv.reader(f)
                    next(rd)  # Skip header
                    for row in rd:
                        post_id, author, title, content, timestamp, likes = row
                        if isinstance(likes, str):
                            try:
                                likes = json.loads(likes)
                            except Exception:
                                likes = []
                        self.posts_database[post_id] = Post(
                            post_id=post_id,
                            author=author,
                            title=title,
                            content=content,
                            timestamp=datetime.fromisoformat(timestamp),
                            likes=likes,
                        )
            except Exception as e:
                logging.error(f"Error loading posts: {e}")

        # Load comments
        if os.path.exists(self.comments_store):
            try:
                with open(self.comments_store, "r") as f:
                    rd = csv.reader(f)
                    next(rd)  # Skip header
                    for row in rd:
                        post_id, email, text, timestamp = row
                        self.posts_database[post_id].comments.append(Comment(
                            post_id=post_id,
                            email=email,
                            text=text,
                            timestamp=datetime.fromisoformat(timestamp)
                        ))
            except Exception as e:
                logging.error(f"Error loading comments: {e}")

    def save_data(self):
        # Save users
        try:
            with open(self.users_store, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["email"])
                for email in self.user_database:
                    wr.writerow([email])
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logging.error(f"Error saving users data: {e}")

        # Save writers
        try:
            with open(self.writers_store, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["email", "name", "password"])
                for writer_obj in self.writers_database.values():
                    wr.writerow([
                        writer_obj.email,
                        writer_obj.name,
                        writer_obj.password.decode('utf-8')
                    ])
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logging.error(f"Error saving writers data: {e}")

        # Save posts
        try:
            with open(self.posts_store, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["post_id", "author", "title", "content", "timestamp", "likes"])
                for post_id, post_obj in self.posts_database.items():
                    wr.writerow([
                        post_id,
                        post_obj.author,
                        post_obj.title,
                        post_obj.content,
                        post_obj.timestamp.isoformat(),
                        post_obj.likes
                    ])
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logging.error(f"Error saving posts data: {e}")

        # Save comments
        try:
            with open(self.comments_store, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["post_id", "email", "text", "timestamp"])
                for post_id, post_obj in self.posts_database.items():
                    for comment in post_obj.comments:
                        wr.writerow([
                            post_id,
                            comment.email,
                            comment.text,
                            comment.timestamp.isoformat()
                        ])
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logging.error(f"Error saving comments data: {e}")

    # --------------------------------------------------------------------------
    # Blog operations application
    # --------------------------------------------------------------------------
    def apply_blog_operation(self, entry: RaftLogEntry):
        op = entry.operation
        params = entry.params
        
        if op == "SUBSCRIBE":
            if len(params) != 1:
                return
            email = params[0]
            if email not in self.user_database:
                self.user_database[email] = User(email)

        elif op == "CREATE_ACCOUNT":
            if len(params) != 3:
                return
            name, email, password = params
            if email not in self.writers_database:
                self.writers_database[email] = Writer(
                    email=email,
                    name=name,
                    password=password
                )

        elif op == "COMMENT_POST":
            if len(params) != 3: 
                return 
            post_id, email, text = params
            comment = Comment(
                post_id=post_id,
                email=email,
                text=text,
                timestamp=datetime.now()
            )
            self.posts_database[post_id].comments.append(comment)
            
        elif op == "CREATE_POST":
            if len(params) < 5:
                return
            post_id, title, content, author, timestamp = params
            
            post = Post(
                post_id=post_id,
                author=author,
                title=title,
                content=content,
                timestamp=datetime.fromisoformat(timestamp)
            )
            
            self.posts_database[post_id] = post
            
            # if post_id not in [author].posts:
            #     self.user_database[author].posts.append(post_id)
            
            # Notify followers via email
            # self.notify_followers_of_new_post(author, post)
                
        elif op == "LIKE_POST":
            if len(params) < 2:
                return
            post_id, username = params
            if post_id in self.posts_database and username in self.user_database:
                self.posts_database[post_id].like(username)
                
        elif op == "UNLIKE_POST":
            if len(params) < 2:
                return
            post_id, username = params
            if post_id in self.posts_database and username in self.user_database:
                self.posts_database[post_id].unlike(username)
                

        elif op == "DELETE_POST":
            if len(params) < 2:
                return
            post_id, author = params
            if post_id in self.posts_database and author == self.posts_database[post_id].author:
                if post_id in self.user_database[author].posts:
                    self.user_database[author].posts.remove(post_id)
                del self.posts_database[post_id]
                
        elif op == "DELETE_ACCOUNT":
            if len(params) < 1:
                return
            username = params[0]
            if username in self.user_database:
                # Remove user from followers/following lists
                for user in self.user_database.values():
                    if username in user.followers:
                        user.followers.remove(username)
                    if username in user.subscriptions:
                        user.subscriptions.remove(username)
                
                # Remove user's posts
                for post_id in list(self.user_database[username].posts):
                    if post_id in self.posts_database:
                        del self.posts_database[post_id]
                
                # Remove user
                del self.user_database[username]
        elif op == "ADD_REPLICA":
            cfg_str = params[0]
            new_cfg = json.loads(cfg_str)
            self.add_replica_local(new_cfg)
        elif op == "REMOVE_REPLICA":
            rid = params[0]
            self.remove_replica_local(rid)

    def notify_followers_of_new_post(self, author, post):
        pass

    def add_replica_local(self, new_cfg):
        arr = get_replicas_config()
        found = any(r["id"] == new_cfg["id"] for r in arr)
        if not found:
            arr.append(new_cfg)
            with open("replicas.json", "w") as f:
                json.dump({"replicas": arr}, f, indent=2)
        self._stubs_cache = {}
        self.replicas_config = arr
        self.raft_node.nextIndex[new_cfg["id"]] = len(self.raft_node.log) + 1
        self.raft_node.matchIndex[new_cfg["id"]] = 0

    def remove_replica_local(self, rid):
        arr = get_replicas_config()
        updated = [r for r in arr if r["id"] != rid]
        with open("replicas.json", "w") as f:
            json.dump({"replicas": updated}, f, indent=2)

        # Remove from stubs
        if rid in self._stubs_cache:
            del self._stubs_cache[rid]
        # Remove from nextIndex, matchIndex
        if rid in self.raft_node.nextIndex:
            del self.raft_node.nextIndex[rid]
        if rid in self.raft_node.matchIndex:
            del self.raft_node.matchIndex[rid]

        self.replicas_config = updated

    # --------------------------------------------------------------------------
    # Replication
    # --------------------------------------------------------------------------
    def replicate_command(self, op, params):
        if self.raft_node.role != "leader":
            return FAILURE
        e = RaftLogEntry(self.raft_node.currentTerm, op, params)
        self.raft_node.log.append(e)
        self.raft_node.save_raft_state()

        # --- IMMEDIATELY COMMIT ON THE LEADER ---
        self.raft_node.commitIndex = len(self.raft_node.log)
        self.apply_committed_entries()

        # Then push out AppendEntries (including the new commitIndex)
        self.send_append_entries_to_all()
        return SUCCESS


    # --------------------------------------------------------------------------
    # Raft RPC
    # --------------------------------------------------------------------------
    # RequestVote RPC - Unchanged from original
    def RequestVote(self, request, context):
        term = request.term
        candId = request.candidateId
        lastLogIndex = request.lastLogIndex
        lastLogTerm = request.lastLogTerm

        # If our term is higher, reject immediately
        if term < self.raft_node.currentTerm:
            return blog_pb2.Response(term=self.raft_node.currentTerm, voteGranted=False)

        # Update term if needed
        if term > self.raft_node.currentTerm:
            self.raft_node.currentTerm = term
            self.raft_node.votedFor = None
            self.raft_node.role = "follower"
            self.raft_node.save_raft_state()

        # Check if we've already voted in this term
        already_voted = self.raft_node.votedFor is not None and self.raft_node.votedFor != candId
        
        # Grant vote if we haven't voted yet and candidate's log is at least as up-to-date as ours
        log_is_current = (lastLogTerm > self.raft_node.last_log_term() or 
                        (lastLogTerm == self.raft_node.last_log_term() and 
                        lastLogIndex >= self.raft_node.last_log_index()))
        
        if not already_voted and log_is_current:
            self.raft_node.votedFor = candId
            self.raft_node.save_raft_state()
            self.reset_election_timer()  # Reset timer when granting vote
            return blog_pb2.Response(term=self.raft_node.currentTerm, voteGranted=True)
        
        return blog_pb2.Response(term=self.raft_node.currentTerm, voteGranted=False)

    # AppendEntries RPC - Unchanged from original
    def AppendEntries(self, request, context):
        if request.term < self.raft_node.currentTerm:
            return blog_pb2.Response(term=self.raft_node.currentTerm, success=False)

        # If the leader's term is higher, update and persist the new term information.
        if request.term > self.raft_node.currentTerm:
            self.raft_node.role = "follower"
            self.raft_node.currentTerm = request.term
            self.raft_node.votedFor = None
            self.raft_node.save_raft_state()  # Force write new term/vote info to disk

        self.reset_election_timer()
        
        prevLogIndex = request.prevLogIndex
        prevLogTerm = request.prevLogTerm

        # Convert incoming entries
        new_entries = [RaftLogEntry(e.term, e.operation, list(e.params))
                        for e in request.entries]

        log_updated = False
        
        # If a follower is completely empty (prevLogIndex == 0),
        # just overwrite its log in one shot.
        if prevLogIndex == 0:
            self.raft_node.log = list(new_entries)
            log_updated = True
            success = True
        else:
            success = self.raft_node.append_entries_to_log(prevLogIndex, prevLogTerm, new_entries)
            if success and new_entries:  # If we actually appended something
                log_updated = True

        if not success:
            return blog_pb2.Response(term=self.raft_node.currentTerm, success=False)

        # Update commit index based on leaderCommit.
        commit_index_changed = False
        if request.leaderCommit > self.raft_node.commitIndex:
            lastNew = len(self.raft_node.log)
            old_commit_index = self.raft_node.commitIndex
            self.raft_node.commitIndex = min(request.leaderCommit, lastNew)
            commit_index_changed = (self.raft_node.commitIndex > old_commit_index)
            
        # Apply any new committed entries and update lastApplied
        if commit_index_changed:
            self.apply_committed_entries()
        
        # After making in-memory updates, write the new Raft state to the JSON file.
        self.raft_node.save_raft_state()
        
        # If the log was updated (either by complete replacement or append), 
        # ensure we save to persistent storage even if no entries were applied yet
        if log_updated and not commit_index_changed and new_entries:
            # This saves data even if the commitIndex hasn't changed yet
            # but we received new log entries that will eventually be committed
            self.save_data()

        return blog_pb2.Response(term=self.raft_node.currentTerm, success=True)

    def RPCGetLeaderInfo(self, request, context):
        if self.raft_node.role == "leader":
            return blog_pb2.Response(operation=blog_pb2.SUCCESS, info=[self.replica_id])
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=[])

    # --------------------------------------------------------------------------
    # Blog RPCs
    # --------------------------------------------------------------------------
    def RPCCreatePost(self, request, context):
        """Create a new blog post"""
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])

        if len(request.info) != 3:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Invalid request format"])

        title, content, author = request.info
        if not title or not content or not author:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing required fields"])

        # Create the post
        post_id = str(uuid.uuid4())
        post = Post(
            post_id=post_id,
            author=author,
            title=title,
            content=content,
            timestamp=datetime.now()
        )
        
        # Replicate the command
        command = "CREATE_POST"
        params = [post_id, title, content, author, post.timestamp.isoformat()]
        success = self.replicate_command(command, params)
        
        if success == SUCCESS:
            # Add post to database
            self.posts_database[post_id] = post
            # Save to disk
            self.save_data()
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
            
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Failed to replicate post"])

    def RPCLogin(self, request, context):
        if len(request.info) != 2:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing email/password"])
            
        email, password = request.info
        
        try:
            validate_email(email)
        except EmailNotValidError:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Invalid email format"])
            
        if email not in self.writers_database:
            # Use same error message as invalid password for security
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Invalid credentials"])
            
        writer = self.writers_database[email]
        if not writer.verify_password(password):
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Invalid credentials"])
            
        return blog_pb2.Response(operation=blog_pb2.SUCCESS)

    def RPCCreateAccount(self, request, context):
        # TODO - this logic needs to be in all RPCs!
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])

        if len(request.info) != 3:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing name/email/password"])
            
        name, email, password = request.info
        
        try:
            validate_email(email)
        except EmailNotValidError:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Invalid email format"])
            
        if len(password) < 8:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Password must be at least 8 characters"])
            
        if email in self.writers_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Email already taken"])
            
        # Create account through Raft to ensure consistency
        op = "CREATE_ACCOUNT"
        params = [name, email, password]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            self.save_data()
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not create account"])

    def RPCLogout(self, request, context):
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing user"])
        email = request.info[0]
        if email in self.writers_database:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not an account"])

    def RPCSubscribe(self, request, context):
        # TODO - this logic needs to be in all RPCs!
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) != 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing email"])
        email = request.info[0]
        try:
            validate_email(email)
            # Email is valid
        except EmailNotValidError:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Email must be a valid email"])
        if email in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Email already taken"])
        op = "SUBSCRIBE"
        params = [email]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            self.save_data()
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCCommentPost(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) <3: 
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post_id/email/text"])
        post_id, email, text = request.info
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post does not exist"])
        if email not in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User does not exist"])
        
        op = "COMMENT_POST"
        params = [post_id, email, text]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            self.posts_database[post_id].comments.append(Comment(post_id, email, text, datetime.now()))
            self.save_data()
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCGetComments(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post_id"])
        post_id = request.info[0]
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post does not exist"])
        
        return blog_pb2.Response(operation=blog_pb2.SUCCESS, info=[post_id, self.posts_database[post_id].comments])

    def RPCSearchUsers(self, request, context):
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing email"])
        email = request.info[0]
        
        for username in self.user_database:
            if email == username:
                return blog_pb2.Response(operation=blog_pb2.SUCCESS, info=[username])
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User not found"])

    def RPCLikePost(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 2:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post_id/username"])
        
        post_id, username = request.info
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post does not exist"])
        if username not in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User does not exist"])
        
        if username in self.posts_database[post_id].likes:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post already liked"])
        
        op = "LIKE_POST"
        params = [post_id, username]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    
    def RPCUnlikePost(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 2:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post_id/username"])
        
        post_id, username = request.info
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post does not exist"])
        if username not in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User does not exist"])
        
        # Check if user has liked the post
        if username not in self.posts_database[post_id].likes:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post not liked"])
        
        op = "UNLIKE_POST"
        params = [post_id, username]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCDeletePost(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 2:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post_id/author"])
        
        post_id, author = request.info
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post does not exist"])
        if author != self.posts_database[post_id].author:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not post owner"])
        
        op = "DELETE_POST"
        params = [post_id, author]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCDeleteAccount(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing username"])
        
        username = request.info[0]
        if username not in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User does not exist"])
        
        op = "DELETE_ACCOUNT"
        params = [username]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCGetAllPosts(self, request, context): 
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        
        posts = list(self.posts_database.values())
        return blog_pb2.Response(
            operation=blog_pb2.SUCCESS,
            posts=[post_obj.to_proto() for post_obj in posts]
            )

    def RPCGetPost(self, request, context):
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing post ID"])
        
        post_id = request.info[0]
        if post_id not in self.posts_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Post not found"])
        
        post = self.posts_database[post_id]
        return blog_pb2.Response(
            operation=blog_pb2.SUCCESS,
            posts=[post.to_proto()]
        )

    # def RPCGetUserPosts(self, request, context):
    #     if len(request.info) < 1:
    #         return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing username"])
        
    #     username = request.info[0]
    #     if username not in self.user_database:
    #         return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User not found"])
        
    #     user_posts = []
    #     for post_id in self.user_database[username].posts:
    #         if post_id in self.posts_database:
    #             post = self.posts_database[post_id]
    #             user_posts.append(post.to_proto())
        
    #     return blog_pb2.Response(operation=blog_pb2.SUCCESS, posts=user_posts)

    def RPCGetNotifications(self, request, context):
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing username"])
        
        username = request.info[0]
        if username not in self.user_database:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["User not found"])
        
        notifications = self.user_database[username].unread_notifications
        # Convert notifications to strings
        notification_strings = [json.dumps(n) for n in notifications]
        
        # Clear unread notifications
        self.user_database[username].unread_notifications = []
        
        return blog_pb2.Response(operation=blog_pb2.SUCCESS, notifications=notification_strings)

    def RPCAddReplica(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing replica config"])
        
        cfg_str = request.info[0]
        op = "ADD_REPLICA"
        params = [cfg_str]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

    def RPCRemoveReplica(self, request, context):
        if self.raft_node.role != "leader":
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Not leader"])
        if len(request.info) < 1:
            return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Missing replica ID"])
        
        replica_id = request.info[0]
        op = "REMOVE_REPLICA"
        params = [replica_id]
        res = self.replicate_command(op, params)
        
        if res == SUCCESS:
            return blog_pb2.Response(operation=blog_pb2.SUCCESS)
        return blog_pb2.Response(operation=blog_pb2.FAILURE, info=["Could not replicate"])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Replica ID")
    args = parser.parse_args()

    # Find the replica config
    replicas = get_replicas_config()
    replica_config = next((r for r in replicas if r["id"] == args.id), None)
    if not replica_config:
        print(f"Error: No replica found with ID {args.id}")
        exit(1)

    # Create and start the server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    blog_server = Server(replica_config)
    blog_pb2_grpc.add_BlogServicer_to_server(blog_server, server)
    
    # Add secure port
    server.add_insecure_port(f"{replica_config['host']}:{replica_config['port']}")
    
    print(f"Starting server {args.id} on {replica_config['host']}:{replica_config['port']}")
    server.start()
    
    # Keep the server running
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)