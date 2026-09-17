"""One-command demo launcher: starts the API in a background thread and seeds it
with demo data, all in a single terminal -- no second window needed.

Usage:
    python run_demo.py

Starts fresh each time (deletes any existing data/audit.db first), waits for the
API to come up, seeds 12 transactions across all 8 controls (see demo_seed.py),
then leaves the server running in the foreground. Open http://127.0.0.1:8000/docs
(or your DEV_SERVER_PORT) and follow docs/demo_script.md. Ctrl+C to stop.
"""

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("COMPLIANCE_ALLOW_INSECURE_HEADERS", "true")
os.environ.setdefault("COMPLIANCE_STORAGE_BACKEND", "sqlite")

import httpx
import uvicorn

PORT = int(os.environ.get("DEV_SERVER_PORT", "8000"))
BASE_URL = f"http://127.0.0.1:{PORT}"
DB_PATH = Path(__file__).resolve().parent / "data" / "audit.db"


def _run_server() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=False, log_level="warning")


def _wait_for_health(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE_URL}/health", timeout=1.0).status_code == 200:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.25)
    return False


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    print(f"Starting API on {BASE_URL} ...")
    if not _wait_for_health():
        print("API did not come up in time.", file=sys.stderr)
        sys.exit(1)

    print("API is up. Seeding demo data...\n")
    import demo_seed

    demo_seed.BASE_URL = BASE_URL
    demo_seed.main()

    print(f"\nReady. Open {BASE_URL}/docs in your browser and follow docs/demo_script.md.")
    print("Leave this window alone (avoid clicking/selecting text in it) -- Ctrl+C here to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
