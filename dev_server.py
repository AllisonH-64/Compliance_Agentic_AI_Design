"""Local dev server launcher (not part of the deployed app).

Sets dev-only defaults -- insecure header auth (X-User-Id/X-User-Role) instead of a
signed JWT, and the SQLite storage backend -- so the API is easy to exercise
manually via /docs without first minting a token. See README.md's "Run locally"
section for the equivalent manual `uvicorn` invocation and full auth options.

Reload defaults OFF: uvicorn's --reload (StatReload) runs a reloader parent
process plus a separate child worker process. On this machine, killing "the"
dev server left one of those processes still holding the port -- so a later
restart silently failed to bind while curl kept hitting the orphaned old worker,
which looked exactly like a code fix not taking effect. Single-process (no
reload) means killing it actually kills it. Set DEV_SERVER_RELOAD=true to opt
back in if you're actively editing code and want auto-restart; if you do,
restart by fully killing the process (not just editing a file) when in doubt.
Set DEV_SERVER_PORT to use a different port, e.g. if 8000 is ever stuck.
"""

import os

os.environ.setdefault("COMPLIANCE_ALLOW_INSECURE_HEADERS", "true")
os.environ.setdefault("COMPLIANCE_STORAGE_BACKEND", "sqlite")

import uvicorn

RELOAD = os.environ.get("DEV_SERVER_RELOAD", "false").strip().lower() in {"1", "true", "yes", "on"}
PORT = int(os.environ.get("DEV_SERVER_PORT", "8000"))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=RELOAD)
