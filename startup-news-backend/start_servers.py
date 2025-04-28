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

def read_process_output(process, timeout=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        line = process.stdout.readline()
        if line:
            print(line.strip(), flush=True)  # Print server output immediately
        
        # Check if process is still running
        if process.poll() is not None:
            print(f"Server exited with code {process.poll()}", flush=True)
            # Get any remaining output
            remaining = process.stdout.read()
            if remaining:
                print(remaining.strip(), flush=True)
            return False
        
        time.sleep(0.1)
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
                ["python", "-u", "server.py", "--id", r["id"]],  # Added -u flag
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                env=env  # Pass modified environment
            )
            print(f"  → Started {r['id']} (PID {p.pid})", flush=True)
            processes.append((r['id'], p))
        else:
            print(f"Port {r['port']} is in use, skipping {r['id']}")

    # Monitor all servers for 5 seconds to ensure they start properly
    if processes:
        print("\nMonitoring server startup:", flush=True)
        for rid, p in processes:
            if read_process_output(p):
                print(f"Server {rid} appears to be running", flush=True)
            else:
                print(f"Server {rid} may have failed to start", flush=True)
        print(f"\nStarted {len(processes)} new servers", flush=True)
    else:
        print("No new servers started.", flush=True)

    # Keep the script running to maintain the server processes
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

if __name__ == "__main__":
    main()