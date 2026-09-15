"""Storage backend dispatcher.

Selected via COMPLIANCE_STORAGE_BACKEND (default "sqlite"). Local dev and the test
suite never set this, so they always run against app/storage_sqlite.py with zero
dependency on boto3 or a real AWS account. Setting it to "dynamodb" (done by the
Lambda deployment in infra/) switches every call in this module to
app/storage_dynamodb.py instead — callers (app/main.py) import from here and never
need to know which backend is active.

storage_dynamodb imports boto3, so it's imported lazily here rather than at module
load time — importing app.storage must not require boto3 to be installed unless the
DynamoDB backend is actually selected.
"""

import os

_BACKEND = os.getenv("COMPLIANCE_STORAGE_BACKEND", "sqlite")

if _BACKEND == "dynamodb":
    from app.storage_dynamodb import (
        get_decision,
        get_review,
        init_db,
        list_decisions,
        list_review_queue,
        save_decision,
        save_review,
    )
elif _BACKEND == "sqlite":
    from app.storage_sqlite import (
        get_connection,
        get_db_path,
        get_decision,
        get_review,
        init_db,
        list_decisions,
        list_review_queue,
        save_decision,
        save_review,
        set_db_path,
    )
else:
    raise ValueError(f"Unknown COMPLIANCE_STORAGE_BACKEND: {_BACKEND!r} (expected 'sqlite' or 'dynamodb')")
