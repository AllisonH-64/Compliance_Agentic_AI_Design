"""Local dev server launcher (not part of the deployed app).

Sets dev-only defaults -- insecure header auth (X-User-Id/X-User-Role) instead of a
signed JWT, and the SQLite storage backend -- so the API is easy to exercise
manually via /docs without first minting a token. See README.md's "Run locally"
section for the equivalent manual `uvicorn` invocation and full auth options.
"""

import os

os.environ.setdefault("COMPLIANCE_ALLOW_INSECURE_HEADERS", "true")
os.environ.setdefault("COMPLIANCE_STORAGE_BACKEND", "sqlite")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
