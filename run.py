import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request


ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
PYTHON_EXE = sys.executable
IS_WINDOWS = sys.platform == "win32"
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))


def npm_executable() -> str:
    return "npm.cmd" if IS_WINDOWS else "npm"


def ensure_npm_available() -> None:
    if shutil.which(npm_executable()) is None:
        raise RuntimeError("npm not found. Please install Node.js and npm first.")


def ensure_frontend_dependencies() -> None:
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if os.path.isdir(node_modules):
        return
    print("[setup] frontend dependencies not found, running npm install...")
    subprocess.run(
        [npm_executable(), "install"],
        cwd=FRONTEND_DIR,
        check=True,
    )


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_available_port(start_port: int, max_attempts: int = 30) -> int:
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port):
            return port
        port += 1
    raise RuntimeError(f"no available frontend port in range [{start_port}, {start_port + max_attempts - 1}]")


def wait_for_api(port: int, timeout_sec: int = 120) -> bool:
    print("[wait] waiting for backend health check...")
    deadline = time.time() + timeout_sec
    url = f"http://127.0.0.1:{port}/api/v1/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    print("[ok] backend is ready")
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_process(cmd: list[str], cwd: str, env: dict[str, str]) -> subprocess.Popen:
    kwargs = {
        "cwd": cwd,
        "env": env,
    }
    if not IS_WINDOWS:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        proc.terminate()


def main() -> int:
    print("[info] using python:", PYTHON_EXE)
    print("[info] cwd:", ROOT_DIR)
    print("[info] backend:", BACKEND_PORT, "frontend:", FRONTEND_PORT)

    ensure_npm_available()
    ensure_frontend_dependencies()

    env = dict(os.environ)
    env["PYTHONPATH"] = BACKEND_DIR

    actual_frontend_port = find_available_port(FRONTEND_PORT)
    if actual_frontend_port != FRONTEND_PORT:
        print(
            f"[warn] frontend port {FRONTEND_PORT} is in use, "
            f"using {actual_frontend_port} instead."
        )

    backend_cmd = [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(BACKEND_PORT),
    ]
    frontend_cmd = [
        npm_executable(),
        "run",
        "dev",
        "--",
        "--host",
        "0.0.0.0",
        "--port",
        str(actual_frontend_port),
    ]

    backend_proc = None
    frontend_proc = None

    try:
        if is_port_in_use(BACKEND_PORT):
            raise RuntimeError(
                f"backend port {BACKEND_PORT} is already in use. "
                "Stop old backend process first, then retry."
            )

        print("[start] launching backend...")
        backend_proc = start_process(backend_cmd, BACKEND_DIR, env)

        if not wait_for_api(BACKEND_PORT):
            raise RuntimeError("backend health check timeout.")

        print("[start] launching frontend...")
        frontend_proc = start_process(frontend_cmd, FRONTEND_DIR, env)

        print()
        print("MediGenius is running:")
        print(f"  Frontend: http://127.0.0.1:{actual_frontend_port}")
        print(f"  Backend : http://127.0.0.1:{BACKEND_PORT}")
        print("Press Ctrl+C to stop.")

        while True:
            if backend_proc.poll() is not None:
                raise RuntimeError("backend process exited unexpectedly.")
            if frontend_proc.poll() is not None:
                raise RuntimeError("frontend process exited unexpectedly.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[stop] stopping services...")
    except Exception as exc:
        print(f"[error] {exc}")
        return 1
    finally:
        stop_process(frontend_proc)
        stop_process(backend_proc)
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
