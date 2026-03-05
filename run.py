import os, sys, time, subprocess, urllib.request
from threading import Thread

VENV_DIR = ".venv"
IS_WINDOWS = sys.platform == "win32"
PYTHON_EXE = sys.executable

def setup():
    # Auto-install dependencies
    if os.path.exists("backend/requirements.txt"):
        print("Checking backend deps...")
        # Use the current python to install requirements
        subprocess.run([PYTHON_EXE, "-m", "pip", "install", "-r", "backend/requirements.txt", "--quiet"])
    
    if not os.path.exists("frontend/node_modules"):
        print("Installing frontend deps...")
        subprocess.run("npm install", cwd="frontend", shell=True)

def wait_for_api():
    print("Waiting for backend...")
    for _ in range(60):
        try:
            if urllib.request.urlopen("http://localhost:8000/api/v1/health").status == 200:
                print("Backend ready!")
                return True
        except: pass
        time.sleep(2)

if __name__ == "__main__":
    setup()
    
    # Start backend in background using venv's python
    env = {**os.environ, "PYTHONPATH": os.path.abspath("backend")}
    backend_proc = subprocess.Popen(
        [PYTHON_EXE, "-m", "uvicorn", "app.main:app", "--port", "8000"],
        cwd="backend", env=env
    )

    # Wait and launch frontend
    frontend_proc = None
    if wait_for_api():
        frontend_proc = subprocess.Popen("npm run dev", cwd="frontend", shell=True)

    try:
        # Keep the main thread alive to catch KeyboardInterrupt
        if frontend_proc:
            frontend_proc.wait()
        else:
            backend_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
    finally:
        if frontend_proc:
            frontend_proc.terminate()
        backend_proc.terminate()
