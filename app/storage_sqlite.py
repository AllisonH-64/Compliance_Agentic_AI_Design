import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.models import DecisionRecord, ReviewRecord, ReviewQueueItem
from app.storage_common import deserialize_decision, deserialize_review, serialize_decision, serialize_review


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "audit.db"
DB_PATH_ENV_VAR = "COMPLIANCE_AUDIT_DB_PATH"
_db_path_override: Path | None = None


def get_db_path() -> Path:
    if _db_path_override is not None:
        return _db_path_override

    configured_path = os.getenv(DB_PATH_ENV_VAR)
    if configured_path:
        return Path(configured_path)

    return DEFAULT_DB_PATH


def set_db_path(path: str | Path | None) -> None:
    global _db_path_override

    _db_path_override = Path(path) if path is not None else None
    init_db()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                case_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                decision_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                case_id TEXT PRIMARY KEY,
                review_json TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES decisions(case_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                decision_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS review_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                review_json TEXT NOT NULL
            )
            """
        )
        connection.commit()


def save_decision(
    decision_record: DecisionRecord,
    *,
    event_type: str = "decision_saved",
    actor_id: str = "system",
    actor_role: str = "system",
) -> None:
    serialized_record = serialize_decision(decision_record)
    recorded_at = datetime.now(UTC).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO decisions (case_id, transaction_id, decision_json)
            VALUES (?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                transaction_id = excluded.transaction_id,
                decision_json = excluded.decision_json
            """,
            (
                decision_record.case_id,
                decision_record.transaction_id,
                serialized_record,
            ),
        )
        connection.execute(
            """
            INSERT INTO decision_history (
                case_id,
                event_type,
                actor_id,
                actor_role,
                recorded_at,
                decision_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision_record.case_id,
                event_type,
                actor_id,
                actor_role,
                recorded_at,
                serialized_record,
            ),
        )
        connection.commit()


def list_decisions() -> list[DecisionRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT decision_json FROM decisions ORDER BY case_id"
        ).fetchall()

    return [deserialize_decision(row["decision_json"]) for row in rows]


def get_decision(case_id: str) -> DecisionRecord | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT decision_json FROM decisions WHERE case_id = ?",
            (case_id,),
        ).fetchone()

    if row is None:
        return None

    return deserialize_decision(row["decision_json"])


def save_review(
    review_record: ReviewRecord,
    *,
    event_type: str = "review_saved",
    actor_id: str = "system",
    actor_role: str = "system",
) -> None:
    serialized_record = serialize_review(review_record)
    recorded_at = datetime.now(UTC).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO reviews (case_id, review_json)
            VALUES (?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                review_json = excluded.review_json
            """,
            (
                review_record.case_id,
                serialized_record,
            ),
        )
        connection.execute(
            """
            INSERT INTO review_history (
                case_id,
                event_type,
                actor_id,
                actor_role,
                recorded_at,
                review_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                review_record.case_id,
                event_type,
                actor_id,
                actor_role,
                recorded_at,
                serialized_record,
            ),
        )
        connection.commit()


def get_review(case_id: str) -> ReviewRecord | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT review_json FROM reviews WHERE case_id = ?",
            (case_id,),
        ).fetchone()

    if row is None:
        return None

    return deserialize_review(row["review_json"])


def list_review_queue() -> list[ReviewQueueItem]:
    decisions = list_decisions()
    queue_items: list[ReviewQueueItem] = []

    for decision in decisions:
        if not decision.review_required:
            continue

        review_record = get_review(decision.case_id)

        if review_record is not None:
            continue

        queue_items.append(
            ReviewQueueItem(
                decision_record=decision,
                review_record=review_record,
            )
        )

    return queue_items
