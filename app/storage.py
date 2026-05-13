import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.engine import load_rule
from app.models import DecisionRecord, ReviewRecord, ReviewQueueItem, ReviewStatus


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
                incident_id TEXT NOT NULL,
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
    serialized_record = json.dumps(decision_record.model_dump(mode="json"))
    recorded_at = datetime.now(UTC).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO decisions (case_id, incident_id, decision_json)
            VALUES (?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                incident_id = excluded.incident_id,
                decision_json = excluded.decision_json
            """,
            (
                decision_record.case_id,
                decision_record.incident_id,
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


def _deserialize_decision(payload: str) -> DecisionRecord:
    raw_record = json.loads(payload)

    raw_rule_metadata = raw_record.get("rule_metadata", {})
    control_id = raw_rule_metadata.get("control_id")

    if control_id is not None:
        try:
            current_rule = load_rule(control_id).model_dump(mode="json")
            raw_record["rule_metadata"] = {**current_rule, **raw_rule_metadata}
        except ValueError:
            raw_record["rule_metadata"] = raw_rule_metadata

    if "review_status" not in raw_record:
        raw_record["review_status"] = (
            ReviewStatus.PENDING if raw_record.get("review_required") else ReviewStatus.NOT_REQUIRED
        )

    raw_record.setdefault("final_reviewer_outcome", None)
    raw_record.setdefault("final_reviewed_at", None)
    raw_record.setdefault("assigned_reviewer_id", None)
    raw_record.setdefault("assigned_at", None)
    raw_record.setdefault("review_started_at", None)
    raw_record.setdefault("risk_band", "low")
    raw_record.setdefault("risk_score", 0.0)
    raw_record.setdefault("triggered_signal_ids", [])
    raw_record.setdefault("signal_rationale", [])
    raw_record.setdefault("escalation_decision", "auto_close")
    raw_record.setdefault("escalation_policy_version", "risk-signals-v1")
    raw_record.setdefault("review_cycle_id", 1)
    raw_record.setdefault("reopen_reason", None)

    return DecisionRecord(**raw_record)


def _deserialize_review(payload: str) -> ReviewRecord:
    raw_record = json.loads(payload)
    raw_record.setdefault("final_decision", None)
    return ReviewRecord(**raw_record)


def list_decisions() -> list[DecisionRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT decision_json FROM decisions ORDER BY case_id"
        ).fetchall()

    return [_deserialize_decision(row["decision_json"]) for row in rows]


def get_decision(case_id: str) -> DecisionRecord | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT decision_json FROM decisions WHERE case_id = ?",
            (case_id,),
        ).fetchone()

    if row is None:
        return None

    return _deserialize_decision(row["decision_json"])


def save_review(
    review_record: ReviewRecord,
    *,
    event_type: str = "review_saved",
    actor_id: str = "system",
    actor_role: str = "system",
) -> None:
    serialized_record = json.dumps(review_record.model_dump(mode="json"))
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

    return _deserialize_review(row["review_json"])


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
