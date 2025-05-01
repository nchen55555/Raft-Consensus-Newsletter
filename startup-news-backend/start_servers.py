import subprocess
import json
import socket
import sys
import time
import os
import argparse

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('10.250.89.39', port))
            return False
        except socket.error:
            return True

def main():
    parser = argparse.ArgumentParser(description='Start Startup News server replicas')
    parser.add_argument('--replicas', type=str, nargs='+', help='List of replica IDs to start (e.g., replica1 replica2)')
    parser.add_argument('--all', action='store_true', help='Start all replicas')
    args = parser.parse_args()

    if not args.replicas and not args.all:
        parser.error('Must specify either --replicas or --all')

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

    # Monitor all servers simultaneously for 5 seconds to ensure they start properly
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