import json

from app.engine import load_rule
from app.models import DecisionRecord, ReviewRecord, ReviewStatus


def deserialize_decision(payload: str) -> DecisionRecord:
    """Backward-compatible decision deserialization shared by every storage backend.
    New fields get defaults here once, rather than duplicated per backend."""
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
    raw_record.setdefault("escalation_policy_version", "vendor-due-diligence-v1")
    raw_record.setdefault("escalation_recipients", [])
    raw_record.setdefault("review_cycle_id", 1)
    raw_record.setdefault("reopen_reason", None)

    return DecisionRecord(**raw_record)


def deserialize_review(payload: str) -> ReviewRecord:
    raw_record = json.loads(payload)
    raw_record.setdefault("final_decision", None)
    return ReviewRecord(**raw_record)


def serialize_decision(decision_record: DecisionRecord) -> str:
    return json.dumps(decision_record.model_dump(mode="json"))


def serialize_review(review_record: ReviewRecord) -> str:
    return json.dumps(review_record.model_dump(mode="json"))
