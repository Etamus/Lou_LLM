"""Launcher that starts the Neve web backend and opens the UI in the browser."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
import types
import atexit


def _load_backend_module():
    backend_root = Path(__file__).resolve().parent / "neve-frontend" / "backend"
    module_path = backend_root / "server.py"

    package_name = "backend"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(backend_root)]
        sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(f"{package_name}.server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError("Nao foi possivel carregar o backend do Neve")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backend_module = _load_backend_module()
DEFAULT_HOST = backend_module.DEFAULT_HOST
DEFAULT_PORT = backend_module.DEFAULT_PORT
create_server = backend_module.create_server


def main() -> int:
    host = os.environ.get("LOU_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LOU_PORT", DEFAULT_PORT))
    server = create_server(host, port)
    url = f"http://{host}:{port}"

    # Graceful shutdown on Ctrl+C
    shutdown_event = threading.Event()

    def _cleanup():
        if shutdown_event.is_set():
            return
        shutdown_event.set()
        with contextlib.suppress(Exception):
            server.server_close()

    atexit.register(_cleanup)

    def _signal_handler(sig, frame):
        print("\n[Lou] Encerrando...")
        shutdown_event.set()
        with contextlib.suppress(Exception):
            server.server_close()
        print("[Lou] Servidor encerrado.")
        os._exit(0)

    signal.signal(signal.SIGINT, _signal_handler)

    print(f"[Lou] Backend escutando em {url}")
    print("[Lou] Pressione Ctrl+C para encerrar.\n")

    # Open the browser after a brief delay so the server is ready
    def _open_browser():
        time.sleep(0.4)
        if not shutdown_event.is_set():
            webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()
        print("[Lou] Servidor encerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
