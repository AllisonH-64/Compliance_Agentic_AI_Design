import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import DecisionRecord, DecisionState, ReviewStatus, RuleMetadata, TransactionCase


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "rules" / "approval_thresholds.json"


def load_rule() -> RuleMetadata:
    with RULES_PATH.open("r", encoding="utf-8") as rule_file:
        raw_rule = json.load(rule_file)

    return RuleMetadata(**raw_rule)


def evaluate_transaction_case(transaction_case: TransactionCase) -> DecisionRecord:
    rule = load_rule()
    evaluated_at = datetime.now(UTC).isoformat()
    evidence_references = [
        f"transaction:{transaction_case.transaction_id}",
    ]

    if transaction_case.approval_record is not None:
        evidence_references.append("approval_record:attached")

    if transaction_case.amount < rule.threshold_amount:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.COMPLIANT,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Transaction amount is below the approval threshold and does not require escalation."
            ),
            severity_score=0.1,
            confidence_score=0.97,
            recommended_action="Close the case as compliant.",
            evidence_references=evidence_references,
            review_required=False,
            review_status=ReviewStatus.NOT_REQUIRED,
            rule_metadata=rule,
        )

    if transaction_case.approval_record is None:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Transaction exceeds the approval threshold but no approval record was provided."
            ),
            severity_score=0.75,
            confidence_score=0.9,
            recommended_action="Route to human review and request the missing approval evidence.",
            evidence_references=evidence_references,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    approval_record = transaction_case.approval_record
    evidence_references.append(f"approver_role:{approval_record.approver_role}")

    if not approval_record.approved:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.NON_COMPLIANT,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Transaction exceeds the approval threshold and the attached approval record is marked not approved."
            ),
            severity_score=0.88,
            confidence_score=0.95,
            recommended_action="Block fulfillment and route the case to a compliance analyst.",
            evidence_references=evidence_references,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if approval_record.approver_role != rule.required_approver_role:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Transaction exceeds the approval threshold, but the attached approval came from a role that does not match the policy requirement."
            ),
            severity_score=0.7,
            confidence_score=0.84,
            recommended_action="Send to human review to validate delegated approval authority.",
            evidence_references=evidence_references,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    return DecisionRecord(
        case_id=transaction_case.case_id,
        transaction_id=transaction_case.transaction_id,
        decision=DecisionState.COMPLIANT,
        evaluated_at=evaluated_at,
        reasoning_summary=(
            "Transaction exceeds the threshold and includes a valid approval from the required role."
        ),
        severity_score=0.2,
        confidence_score=0.96,
        recommended_action="Close the case as compliant and retain the approval evidence in the audit trail.",
        evidence_references=evidence_references,
        review_required=False,
        review_status=ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )
