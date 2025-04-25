import subprocess
import json
import socket
import sys
import time
import os

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
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

with open("replicas.json", "r") as f:
    replicas = json.load(f)["replicas"]

# Try to start one server that isn't already running
for r in replicas:
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
        
        # Monitor the server for 5 seconds to ensure it starts properly
        if read_process_output(p):
            print(f"Server {r['id']} appears to be running", flush=True)
        break
else:
    print("All ports are in use. No new server started.", flush=True)
