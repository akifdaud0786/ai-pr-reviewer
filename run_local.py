import subprocess
import sys
import os
import time
import signal

# Ensure PYTHONPATH includes the project root
os.environ["PYTHONPATH"] = os.path.abspath(os.path.dirname(__file__))

services = [
    {"name": "gateway_service", "command": [sys.executable, "-m", "uvicorn", "gateway_service.main:app", "--host", "127.0.0.1", "--port", "8000"]},
    {"name": "webhook_service", "command": [sys.executable, "-m", "uvicorn", "webhook_service.main:app", "--host", "127.0.0.1", "--port", "8001"]},
    {"name": "reviewer_service", "command": [sys.executable, "-m", "uvicorn", "reviewer_service.main:app", "--host", "127.0.0.1", "--port", "8002"]},
    {"name": "learner_service", "command": [sys.executable, "-m", "uvicorn", "learner_service.main:app", "--host", "127.0.0.1", "--port", "8003"]},
]

processes = []

def signal_handler(sig, frame):
    print("\nStopping all services...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)

# Register signals for graceful termination
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    print("Starting all microservices locally...")
    
    # Start each process
    for service in services:
        print(f"Starting {service['name']}...")
        p = subprocess.Popen(
            service["command"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy()
        )
        processes.append(p)
        
        # Give a small delay to avoid port conflicts and let them start up sequentially
        time.sleep(0.5)

    print("\nAll services started! Press Ctrl+C to stop.")
    print("Available services:")
    print("  - Gateway Service:   http://127.0.0.1:8000")
    print("  - Webhook Service:   http://127.0.0.1:8001")
    print("  - Reviewer Service:  http://127.0.0.1:8002")
    print("  - Learner Service:   http://127.0.0.1:8003")
    print("-" * 50)

    # Monitor outputs and print them
    try:
        import threading
        
        def read_output(process, name):
            for line in iter(process.stdout.readline, ""):
                print(f"[{name}] {line.strip()}", flush=True)
            process.stdout.close()

        threads = []
        for p, s in zip(processes, services):
            t = threading.Thread(target=read_output, args=(p, s["name"]), daemon=True)
            t.start()
            threads.append(t)
            
        while True:
            # Check if any process has exited unexpectedly
            for p, s in zip(processes, services):
                ret = p.poll()
                if ret is not None:
                    print(f"\n[ERROR] Service {s['name']} exited with code {ret}!")
                    signal_handler(None, None)
            time.sleep(1)
            
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
