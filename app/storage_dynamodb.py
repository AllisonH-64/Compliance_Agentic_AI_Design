"""DynamoDB-backed storage, selected via COMPLIANCE_STORAGE_BACKEND=dynamodb.

Table lifecycle (creation, indexes, streams) is owned by the CDK app under infra/,
not by this module — init_db() is a no-op here by design, unlike the SQLite backend
where the app itself owns schema creation for local/dev convenience.

Mirrors the SQLite backend's json-blob-per-item shape (decision_json/review_json as
a single string attribute) rather than exploding every field into native DynamoDB
attributes, so app/storage_common.py's deserialization logic is reusable unchanged
and this backend stays a drop-in replacement with the same function signatures.
"""

import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import boto3

from app.models import DecisionRecord, ReviewRecord, ReviewQueueItem
from app.storage_common import deserialize_decision, deserialize_review, serialize_decision, serialize_review


DECISIONS_TABLE_ENV_VAR = "COMPLIANCE_DECISIONS_TABLE"
REVIEWS_TABLE_ENV_VAR = "COMPLIANCE_REVIEWS_TABLE"
DECISION_HISTORY_TABLE_ENV_VAR = "COMPLIANCE_DECISION_HISTORY_TABLE"
REVIEW_HISTORY_TABLE_ENV_VAR = "COMPLIANCE_REVIEW_HISTORY_TABLE"


@lru_cache(maxsize=1)
def _resource():
    # Initialized once per warm Lambda execution environment, not per invocation.
    return boto3.resource("dynamodb")


def _table(env_var: str):
    table_name = os.environ[env_var]
    return _resource().Table(table_name)


def init_db() -> None:
    """No-op: table creation is owned by the CDK app (infra/data_stack.py)."""
    return None


def save_decision(
    decision_record: DecisionRecord,
    *,
    event_type: str = "decision_saved",
    actor_id: str = "system",
    actor_role: str = "system",
) -> None:
    serialized_record = serialize_decision(decision_record)
    recorded_at = datetime.now(UTC).isoformat()

    _table(DECISIONS_TABLE_ENV_VAR).put_item(
        Item={
            "case_id": decision_record.case_id,
            "transaction_id": decision_record.transaction_id,
            "decision_json": serialized_record,
        }
    )
    _table(DECISION_HISTORY_TABLE_ENV_VAR).put_item(
        Item={
            "case_id": decision_record.case_id,
            "event_key": f"{recorded_at}#{uuid.uuid4().hex}",
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "recorded_at": recorded_at,
            "decision_json": serialized_record,
        }
    )


def get_decision(case_id: str) -> DecisionRecord | None:
    response = _table(DECISIONS_TABLE_ENV_VAR).get_item(Key={"case_id": case_id})
    item = response.get("Item")

    if item is None:
        return None

    return deserialize_decision(item["decision_json"])


def list_decisions() -> list[DecisionRecord]:
    table = _table(DECISIONS_TABLE_ENV_VAR)
    items = []
    scan_kwargs: dict = {}

    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

        if "LastEvaluatedKey" not in response:
            break

        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    decisions = [deserialize_decision(item["decision_json"]) for item in items]
    return sorted(decisions, key=lambda decision: decision.case_id)


def save_review(
    review_record: ReviewRecord,
    *,
    event_type: str = "review_saved",
    actor_id: str = "system",
    actor_role: str = "system",
) -> None:
    serialized_record = serialize_review(review_record)
    recorded_at = datetime.now(UTC).isoformat()

    _table(REVIEWS_TABLE_ENV_VAR).put_item(
        Item={
            "case_id": review_record.case_id,
            "review_json": serialized_record,
        }
    )
    _table(REVIEW_HISTORY_TABLE_ENV_VAR).put_item(
        Item={
            "case_id": review_record.case_id,
            "event_key": f"{recorded_at}#{uuid.uuid4().hex}",
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "recorded_at": recorded_at,
            "review_json": serialized_record,
        }
    )


def get_review(case_id: str) -> ReviewRecord | None:
    response = _table(REVIEWS_TABLE_ENV_VAR).get_item(Key={"case_id": case_id})
    item = response.get("Item")

    if item is None:
        return None

    return deserialize_review(item["review_json"])


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
