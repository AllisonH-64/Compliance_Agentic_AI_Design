import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import (
    DEFAULT_CONTROL_ID,
    DecisionRecord,
    DecisionState,
    ReviewQueueMetrics,
    ReviewStatus,
    RuleMetadata,
    TransactionCase,
)


RULES_DIR = Path(__file__).resolve().parents[1] / "data" / "rules"
DEFAULT_SLA_HOURS = 24.0


def load_rules() -> list[RuleMetadata]:
    rules: list[RuleMetadata] = []

    for rule_path in sorted(RULES_DIR.glob("*.json")):
        with rule_path.open("r", encoding="utf-8") as rule_file:
            raw_rule = json.load(rule_file)
        rules.append(RuleMetadata(**raw_rule))

    return rules


def load_rule(control_id: str = DEFAULT_CONTROL_ID) -> RuleMetadata:
    for rule in load_rules():
        if rule.control_id == control_id:
            return rule

    raise ValueError(f"Unknown control_id: {control_id}")


def _build_base_evidence_references(transaction_case: TransactionCase) -> list[str]:
    evidence_references = [
        f"transaction:{transaction_case.transaction_id}",
        f"control:{transaction_case.control_id}",
    ]

    if transaction_case.approval_record is not None:
        evidence_references.append("approval_record:attached")

    if transaction_case.receipt_record is not None:
        evidence_references.append("receipt_record:attached")

        if transaction_case.receipt_record.document_id is not None:
            evidence_references.append(f"receipt_document:{transaction_case.receipt_record.document_id}")

    return evidence_references


def _evaluate_large_transaction_approval(
    transaction_case: TransactionCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    evidence_references = _build_base_evidence_references(transaction_case)

    if transaction_case.amount < rule.threshold_amount:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.COMPLIANT,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Submitted spend is below the pre-approval threshold and does not require escalation."
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
                "Submitted spend exceeds the pre-approval threshold but no approval record was provided."
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
                "Submitted spend exceeds the pre-approval threshold and the attached approval record is marked not approved."
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
                "Submitted spend exceeds the pre-approval threshold, but the attached approval came from a role that does not match the policy requirement."
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
            "Submitted spend exceeds the threshold and includes a valid approval from the required role."
        ),
        severity_score=0.2,
        confidence_score=0.96,
        recommended_action="Close the case as compliant and retain the approval evidence in the audit trail.",
        evidence_references=evidence_references,
        review_required=False,
        review_status=ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_expense_receipt(
    transaction_case: TransactionCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    evidence_references = _build_base_evidence_references(transaction_case)

    if rule.required_currency is not None and transaction_case.currency != rule.required_currency:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "The case was routed to the receipt evidence control, but the submitted currency does not match the configured policy scope."
            ),
            severity_score=0.45,
            confidence_score=0.78,
            recommended_action="Route to human review to confirm whether this case belongs to the receipt evidence policy scope.",
            evidence_references=evidence_references,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if transaction_case.amount < rule.threshold_amount:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.COMPLIANT,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Submitted spend is below the receipt threshold and does not require additional evidence."
            ),
            severity_score=0.08,
            confidence_score=0.97,
            recommended_action="Close the case as compliant.",
            evidence_references=evidence_references,
            review_required=False,
            review_status=ReviewStatus.NOT_REQUIRED,
            rule_metadata=rule,
        )

    if transaction_case.receipt_record is None:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Submitted spend exceeds the receipt threshold but no receipt evidence was provided."
            ),
            severity_score=0.72,
            confidence_score=0.91,
            recommended_action="Route to human review and request the missing receipt evidence.",
            evidence_references=evidence_references,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    receipt_record = transaction_case.receipt_record

    if not receipt_record.attached:
        return DecisionRecord(
            case_id=transaction_case.case_id,
            transaction_id=transaction_case.transaction_id,
            decision=DecisionState.NON_COMPLIANT,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Submitted spend exceeds the receipt threshold and the submitted receipt record explicitly indicates no attachment."
            ),
            severity_score=0.8,
            confidence_score=0.94,
            recommended_action="Hold the case and route it to a compliance analyst.",
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
            "Submitted spend exceeds the receipt threshold and includes the required receipt evidence."
        ),
        severity_score=0.18,
        confidence_score=0.95,
        recommended_action="Close the case as compliant and retain the receipt reference in the audit trail.",
        evidence_references=evidence_references,
        review_required=False,
        review_status=ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def evaluate_transaction_case(transaction_case: TransactionCase) -> DecisionRecord:
    rule = load_rule(transaction_case.control_id)
    evaluated_at = datetime.now(UTC).isoformat()

    if rule.control_domain == "transaction_approval":
        return _evaluate_large_transaction_approval(transaction_case, rule, evaluated_at)

    if rule.control_domain == "expense_receipt":
        return _evaluate_expense_receipt(transaction_case, rule, evaluated_at)

    raise ValueError(f"Unsupported control_domain: {rule.control_domain}")


def calculate_review_queue_metrics(decisions: list[DecisionRecord], sla_target_hours: float = DEFAULT_SLA_HOURS) -> ReviewQueueMetrics:
    active_decisions = [decision for decision in decisions if decision.review_required]

    if not active_decisions:
        return ReviewQueueMetrics(
            active_review_count=0,
            pending_count=0,
            assigned_count=0,
            in_review_count=0,
            breached_sla_count=0,
            average_queue_age_hours=0.0,
            oldest_queue_age_hours=0.0,
            sla_target_hours=sla_target_hours,
        )

    now = datetime.now(UTC)
    queue_ages_hours: list[float] = []
    breached_sla_count = 0

    for decision in active_decisions:
        started_at = datetime.fromisoformat(decision.evaluated_at)
        age_hours = (now - started_at).total_seconds() / 3600
        queue_ages_hours.append(age_hours)

        if age_hours > sla_target_hours:
            breached_sla_count += 1

    return ReviewQueueMetrics(
        active_review_count=len(active_decisions),
        pending_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.PENDING),
        assigned_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.ASSIGNED),
        in_review_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.IN_REVIEW),
        breached_sla_count=breached_sla_count,
        average_queue_age_hours=round(sum(queue_ages_hours) / len(queue_ages_hours), 2),
        oldest_queue_age_hours=round(max(queue_ages_hours), 2),
        sla_target_hours=sla_target_hours,
    )
