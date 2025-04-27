import grpc
import json
import socket
import subprocess
import sys
import time
import uuid
import os
import signal
import threading
from datetime import datetime

# Import generated protobuf code
from protos import blog_pb2, blog_pb2_grpc

class BlogServerTest:
    def __init__(self, replicas_to_start=1):
        self.server_processes = {}
        self.replicas_config = self.load_replicas_config()
        self.leader_stub = None
        self.replicas_to_start = min(replicas_to_start, len(self.replicas_config))

    def load_replicas_config(self):
        with open("replicas.json", "r") as f:
            return json.load(f)["replicas"]

    def is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return False
            except socket.error:
                return True

    def start_servers(self):
        """Start a specified number of replica servers"""
        print(f"Starting {self.replicas_to_start} server replicas...")
        
        started_count = 0
        for replica in self.replicas_config:
            if started_count >= self.replicas_to_start:
                break
                
            replica_id = replica['id']
            port = replica['port']
            
            if not self.is_port_in_use(port):
                print(f"Starting replica {replica_id} on port {port}...")
                
                # Set environment variables for unbuffered output
                env = dict(os.environ)
                env['PYTHONUNBUFFERED'] = '1'
                
                # Start the server process
                process = subprocess.Popen(
                    ["python", "-u", "server.py", "--id", replica_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env
                )
                
                self.server_processes[replica_id] = process
                print(f"Started replica {replica_id} (PID: {process.pid})")
                
                # Wait a bit for server to initialize
                time.sleep(2)
                started_count += 1
            else:
                print(f"Port {port} is already in use. Skipping replica {replica_id}.")
        
        print(f"Started {started_count} server replicas.")
        
        # Wait some more time for Raft election to complete
        print("Waiting for leader election...")
        time.sleep(10)
    
    def monitor_server_output(self):
        """Start a thread to monitor and print server output"""
        def output_reader():
            while self.server_processes:
                for replica_id, process in list(self.server_processes.items()):
                    try:
                        line = process.stdout.readline()
                        if line:
                            print(f"[{replica_id}] {line.strip()}")
                        elif process.poll() is not None:
                            print(f"Server {replica_id} exited with code {process.poll()}")
                            del self.server_processes[replica_id]
                    except:
                        pass
                time.sleep(0.1)
        
        thread = threading.Thread(target=output_reader, daemon=True)
        thread.start()

    def stop_servers(self):
        """Stop all server processes"""
        print("Stopping all server processes...")
        for replica_id, process in self.server_processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"Stopped server {replica_id}")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"Killed server {replica_id} (did not terminate gracefully)")
            except Exception as e:
                print(f"Error stopping server {replica_id}: {e}")
        self.server_processes = {}

    def find_leader(self):
        """Find the current leader in the cluster"""
        for replica in self.replicas_config:
            try:
                channel = grpc.insecure_channel(f"{replica['host']}:{replica['port']}")
                stub = blog_pb2_grpc.BlogStub(channel)
                response = stub.RPCGetLeaderInfo(blog_pb2.Request(), timeout=2.0)
                if response.operation == blog_pb2.SUCCESS and response.info:
                    leader_id = response.info[0]
                    # Find leader config
                    leader_config = next((r for r in self.replicas_config if r["id"] == leader_id), None)
                    if leader_config:
                        print(f"Found leader: {leader_id} at {leader_config['host']}:{leader_config['port']}")
                        return leader_config
            except Exception as e:
                print(f"Error contacting replica {replica['id']}: {e}")
                continue
        
        print("No leader found!")
        return None

    def get_leader_stub(self):
        """Get a gRPC stub for the leader server"""
        leader_config = self.find_leader()
        if not leader_config:
            return None
        
        channel = grpc.insecure_channel(f"{leader_config['host']}:{leader_config['port']}")
        self.leader_stub = blog_pb2_grpc.BlogStub(channel)
        return self.leader_stub

    def test_create_account(self):
        print("\n===== Testing Create Account =====")
        # Generate a unique email to avoid conflicts
        name = "Test User"
        unique_id = uuid.uuid4().hex[:8]
        email = f"testuser{unique_id}@gmail.com"
        password = "password123"
        
        print(f"Creating account: {name} ({email})")
        response = self.leader_stub.RPCCreateAccount(blog_pb2.Request(info=[name, email, password]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Account created successfully")
            return email, password
        else:
            print(f"❌ Failed to create account: {response.info}")
            return None, None

    def test_login(self, email, password):
        print("\n===== Testing Login =====")
        print(f"Logging in with: {email}")
        response = self.leader_stub.RPCLogin(blog_pb2.Request(info=[email, password]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Login successful")
            return True
        else:
            print(f"❌ Login failed: {response.info}")
            return False

    def test_subscribe(self):
        print("\n===== Testing Subscribe =====")
        # Generate a unique email for subscriber
        unique_id = uuid.uuid4().hex[:8] 
        subscriber_email = f"subscriber{unique_id}@gmail.com"
        name = "Subscriber User"
        password = "password123"
        
        print(f"Creating account: {name} ({subscriber_email})")
        response = self.leader_stub.RPCCreateAccount(blog_pb2.Request(info=[name, subscriber_email, password]))
        
        print(f"Creating subscriber: {subscriber_email}")
        response = self.leader_stub.RPCSubscribe(blog_pb2.Request(info=[subscriber_email]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Subscription successful")
            return subscriber_email
        else:
            print(f"❌ Subscription failed: {response.info}")
            return None

    def test_create_post(self, author_email):
        print("\n===== Testing Create Post =====")
        title = "Test Post Title"
        content = "This is a test post content. It's being created as part of an automated test."
        
        print(f"Creating post: '{title}' by {author_email}")
        response = self.leader_stub.RPCCreatePost(blog_pb2.Request(info=[title, content, author_email]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Post created successfully")
            return True
        else:
            print(f"❌ Failed to create post: {response.info}")
            return False

    def test_get_posts(self):
        # This is a placeholder since we don't have an RPCGetAllPosts
        # In a real implementation, we would need a way to get posts or get user posts
        print("\n===== Cannot test getting posts =====")
        print("The server doesn't provide an RPC to get all posts")
        print("We would need to implement RPCGetAllPosts or use RPCGetUserPosts")
        return None

    def test_like_post(self, post_id, user_email):
        print("\n===== Testing Like Post =====")
        print(f"User {user_email} liking post {post_id}")
        response = self.leader_stub.RPCLikePost(blog_pb2.Request(info=[post_id, user_email]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Post liked successfully")
            return True
        else:
            print(f"❌ Failed to like post: {response.info}")
            return False

    def test_unlike_post(self, post_id, user_email):
        print("\n===== Testing Unlike Post =====")
        print(f"User {user_email} unliking post {post_id}")
        response = self.leader_stub.RPCUnlikePost(blog_pb2.Request(info=[post_id, user_email]))
        
        if response.operation == blog_pb2.SUCCESS:
            print("✅ Post unliked successfully")
            return True
        else:
            print(f"❌ Failed to unlike post: {response.info}")
            return False

    def run_test_suite(self):
        try:
            print("Starting blog server test suite...")
            
            # Start servers
            self.start_servers()
            
            # Start monitoring thread
            self.monitor_server_output()
            
            # Get leader stub
            self.get_leader_stub()
            if not self.leader_stub:
                print("Cannot proceed with tests as no leader was found.")
                return
            
            # Run tests
            writer_email, password = self.test_create_account()
            if not writer_email:
                print("Cannot proceed with login test as account creation failed.")
                return
            
            logged_in = self.test_login(writer_email, password)
            if not logged_in:
                print("Login failed, but continuing with other tests...")
            
            subscriber_email = self.test_subscribe()
            if not subscriber_email:
                print("Cannot proceed with like/unlike tests as subscription failed.")
            
            post_created = self.test_create_post(writer_email)
            if not post_created:
                print("Post creation failed, cannot proceed with like/unlike tests.")
                return
            
            # Note: In a real implementation, we would need to get the post ID here
            # We can't demonstrate liking/unliking posts without knowing the post ID
            
            print("\n===== Test Summary =====")
            print(f"Writer account: {writer_email}")
            if subscriber_email:
                print(f"Subscriber account: {subscriber_email}")
            print("All tests completed.")
            
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
        finally:
            print("\nCleaning up...")
            self.stop_servers()
            print("Test suite finished.")

if __name__ == "__main__":
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Blog Server Test Suite")
    parser.add_argument("--replicas", type=int, default=3, help="Number of replicas to start (default: 3)")
    args = parser.parse_args()
    
    # Create and run test suite
    test_suite = BlogServerTest(replicas_to_start=args.replicas)
    test_suite.run_test_suite()