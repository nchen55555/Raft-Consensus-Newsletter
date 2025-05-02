import subprocess
import json
import socket
import sys
import time
import os
import argparse
import uuid
import grpc
from protos import blog_pb2, blog_pb2_grpc

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('10.250.89.39', port))
            return False
        except socket.error:
            return True

def notify_existing_replicas(new_replica):
    """Notify all existing replicas about the new replica."""
    # Load existing replicas
    with open("replicas.json", "r") as f:
        replicas_data = json.load(f)
        all_replicas = replicas_data["replicas"]
    
    # Skip the new replica itself
    existing_replicas = [r for r in all_replicas if r['id'] != new_replica['id']]
    
    if not existing_replicas:
        print("No existing replicas to notify.")
        return True
    
    # Convert the new replica to a JSON string for transmission
    new_replica_json = json.dumps(new_replica)
    
    success = False
    # Try to find the leader and notify it
    for replica in existing_replicas:
        try:
            print(f"Attempting to notify replica {replica['id']} about new replica...")
            channel = grpc.insecure_channel(f"{replica['host']}:{replica['port']}")
            stub = blog_pb2_grpc.BlogStub(channel)
            
            # Create the request with the replica config as info
            request = blog_pb2.Request(info=[new_replica_json])
            
            # Call RPCAddReplica
            response = stub.RPCAddReplica(request, timeout=5)
            
            if response.operation == blog_pb2.SUCCESS:
                print(f"Successfully notified replica {replica['id']} about new replica {new_replica['id']}.")
                success = True
                break  # Successfully notified the leader, no need to continue
            else:
                print(f"Replica {replica['id']} failed to add new replica: {response.info}")
        except Exception as e:
            print(f"Error notifying replica {replica['id']}: {str(e)}")
    
    if success:
        print(f"Successfully added replica {new_replica['id']} to the cluster.")
    else:
        print(f"WARNING: Could not notify any existing replicas about {new_replica['id']}.")
        print("You may need to manually restart all replicas for them to recognize the new one.")
    
    return success

def add_replica(name, host, port, start=True, notify=True):
    # Load existing replicas
    with open("replicas.json", "r") as f:
        replicas_data = json.load(f)
        all_replicas = replicas_data["replicas"]
    
    # Check if name or port already exists
    for r in all_replicas:
        if r['id'] == name:
            print(f"Error: Replica with ID '{name}' already exists.")
            return False
        if r['port'] == port:
            print(f"Error: Port {port} is already assigned to replica '{r['id']}'.")
            return False
    
    # Create new replica config with unique data directories
    new_replica = {
        "id": name,
        "host": host,
        "port": port,
        "raft_store": f"replica_logs/{name}_raft.json",
        "posts_store": f"replica_logs/{name}_posts.csv",
        "users_store": f"replica_logs/{name}_users.csv",
        "writers_store": f"replica_logs/{name}_writers.csv",
        "comments_store": f"replica_logs/{name}_comments.csv"
    }
    
    # Create data directory if it doesn't exist
    os.makedirs("replica_logs", exist_ok=True)
    
    # Add the new replica to the list
    all_replicas.append(new_replica)
    
    # Save updated replicas list
    with open("replicas.json", "w") as f:
        json.dump({"replicas": all_replicas}, f, indent=2)
    
    print(f"Added new replica '{name}' on {host}:{port}")
    
    # Start the new replica if requested
    new_process = None
    if start:
        env = dict(os.environ)
        env['PYTHONUNBUFFERED'] = '1'
        
        new_process = subprocess.Popen(
            ["python", "-u", "server.py", "--id", name],
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env
        )
        print(f"  → Started {name} (PID {new_process.pid})")
        
        # Give the new replica some time to start up before notifying others
        time.sleep(3)
    
    # Notify existing replicas about the new one
    if notify and len(all_replicas) > 1:
        # There's at least one existing replica
        notify_existing_replicas(new_replica)
    
    return new_process if start else True

def main():
    parser = argparse.ArgumentParser(description='Start Startup News server replicas')
    parser.add_argument('--replicas', type=str, nargs='+', help='List of replica IDs to start (e.g., replica1 replica2)')
    parser.add_argument('--all', action='store_true', help='Start all replicas')
    parser.add_argument('--add-replica', action='store_true', help='Add a new replica')
    parser.add_argument('--name', type=str, help='Name for the new replica (required with --add-replica)')
    parser.add_argument('--host', type=str, default='localhost', help='Host for the new replica (default: localhost)')
    parser.add_argument('--port', type=int, help='Port for the new replica (required with --add-replica)')
    parser.add_argument('--no-start', action='store_true', help='Don\'t start the new replica after adding it')
    parser.add_argument('--no-notify', action='store_true', help='Don\'t notify other replicas about the new one')
    args = parser.parse_args()

    # Add a new replica if requested
    if args.add_replica:
        if not args.name or not args.port:
            parser.error('--name and --port are required with --add-replica')
        
        new_process = add_replica(args.name, args.host, args.port, 
                                  not args.no_start, 
                                  not args.no_notify)
        
        if new_process and not args.no_start:
            # Monitor the new replica
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down server...", flush=True)
                try:
                    new_process.terminate()
                    new_process.wait(timeout=5)
                    print(f"Stopped {args.name}", flush=True)
                except:
                    print(f"Failed to stop {args.name} gracefully", flush=True)
                    try:
                        new_process.kill()
                    except:
                        pass
        return

    if not args.replicas and not args.all:
        parser.error('Must specify either --replicas or --all (or use --add-replica)')

    with open("replicas.json", "r") as f:
        all_replicas = json.load(f)["replicas"]

    # Filter replicas based on command line args
    if args.all:
        replicas_to_start = all_replicas
    else:
        replicas_to_start = [r for r in all_replicas if r['id'] in args.replicas]
        if not replicas_to_start:
            print(f"No valid replicas found. Available replicas: {[r['id'] for r in all_replicas]}")
            return

    # Track all started processes
    processes = []

    # Try to start specified servers that aren't already running
    for r in replicas_to_start:
        if not is_port_in_use(r['port']):
            print(f"Launching {r['id']} on port {r['port']}", flush=True)
            # Set PYTHONUNBUFFERED=1 to disable buffering in the Python process
            env = dict(os.environ)
            env['PYTHONUNBUFFERED'] = '1'
            
            p = subprocess.Popen(
                ["python", "-u", "server.py", "--id", r["id"]],
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # Line buffered
                env=env  # Pass modified environment
            )
            print(f"  → Started {r['id']} (PID {p.pid})", flush=True)
            processes.append((r['id'], p))
        else:
            print(f"Port {r['port']} is in use, skipping {r['id']}")

    # Monitor all servers simultaneously to ensure they start properly
    if processes:
        print("\nServers are starting. You should see their output below:", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down servers...", flush=True)
            for rid, p in processes:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                    print(f"Stopped {rid}", flush=True)
                except:
                    print(f"Failed to stop {rid} gracefully", flush=True)
                    try:
                        p.kill()
                    except:
                        pass
    else:
        print("No new servers started.", flush=True)

if __name__ == "__main__":
    main()