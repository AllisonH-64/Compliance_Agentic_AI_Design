import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import (
    ControlSummary,
    DEFAULT_CONTROL_ID,
    DashboardSummary,
    DecisionRecord,
    DecisionState,
    GiftRecipientType,
    MarketRiskLevel,
    NotificationRecipient,
    PolicyReferenceType,
    RiskBand,
    ReviewQueueMetrics,
    ReviewStatus,
    RuleMetadata,
    SignalFrequency,
    VendorEngagementType,
    VendorTransaction,
)


RULES_DIR = Path(__file__).resolve().parents[1] / "data" / "rules"
DEFAULT_SLA_HOURS = 24.0
VENDOR_ESCALATION_VERSION = "vendor-due-diligence-v1"


def validate_no_internal_policy_conflicts(rule: RuleMetadata) -> list[str]:
    """A rule's internal escalation_triggers values must not be looser than any
    verified regulatory floor declared on its own external_regulation policy
    references. Returns human-readable conflict descriptions; an empty list means
    no conflicts. Only checks trigger keys where a real, verified minimum has been
    entered (minimum_threshold_field/minimum_threshold_value) — this deliberately
    does not invent numeric floors that weren't confirmed by research."""
    conflicts: list[str] = []
    triggers = rule.escalation_triggers or {}

    for reference in rule.policy_references:
        if reference.source_type != PolicyReferenceType.EXTERNAL_REGULATION:
            continue
        if reference.minimum_threshold_field is None or reference.minimum_threshold_value is None:
            continue

        internal_value = triggers.get(reference.minimum_threshold_field)
        if isinstance(internal_value, (int, float)) and internal_value > reference.minimum_threshold_value:
            conflicts.append(
                f"{rule.control_id}: internal trigger '{reference.minimum_threshold_field}' "
                f"({internal_value}) is looser than the regulatory minimum "
                f"({reference.minimum_threshold_value}) required by '{reference.citation}'."
            )

    return conflicts


def load_rules() -> list[RuleMetadata]:
    rules: list[RuleMetadata] = []

    for rule_path in sorted(RULES_DIR.glob("*.json")):
        with rule_path.open("r", encoding="utf-8") as rule_file:
            raw_rule = json.load(rule_file)
        rule = RuleMetadata(**raw_rule)

        conflicts = validate_no_internal_policy_conflicts(rule)
        if conflicts:
            raise ValueError("; ".join(conflicts))

        rules.append(rule)

    return rules


def load_rule(control_id: str = DEFAULT_CONTROL_ID) -> RuleMetadata:
    for rule in load_rules():
        if rule.control_id == control_id:
            return rule

    raise ValueError(f"Unknown control_id: {control_id}")


def _build_base_evidence_references(vendor_transaction: VendorTransaction) -> list[str]:
    evidence_references = [
        f"transaction:{vendor_transaction.transaction_id}",
        f"control:{vendor_transaction.control_id}",
        f"vendor:{vendor_transaction.vendor_id or vendor_transaction.vendor_name}",
    ]

    if vendor_transaction.approval_record is not None:
        evidence_references.append("approval_record:attached")

        if vendor_transaction.approval_record.document_id is not None:
            evidence_references.append(f"approval_document:{vendor_transaction.approval_record.document_id}")

    if vendor_transaction.second_approval_record is not None:
        evidence_references.append("second_approval_record:attached")

        if vendor_transaction.second_approval_record.document_id is not None:
            evidence_references.append(
                f"second_approval_document:{vendor_transaction.second_approval_record.document_id}"
            )

    if vendor_transaction.vendor_screening_record is not None:
        evidence_references.append("vendor_screening_record:attached")

        if vendor_transaction.vendor_screening_record.document_id is not None:
            evidence_references.append(
                f"vendor_screening_document:{vendor_transaction.vendor_screening_record.document_id}"
            )

    if vendor_transaction.conflict_of_interest_record is not None:
        evidence_references.append("conflict_of_interest_record:attached")

        if vendor_transaction.conflict_of_interest_record.document_id is not None:
            evidence_references.append(
                f"conflict_of_interest_document:{vendor_transaction.conflict_of_interest_record.document_id}"
            )

    if vendor_transaction.receipt_record is not None:
        evidence_references.append("receipt_record:attached")

        if vendor_transaction.receipt_record.document_id is not None:
            evidence_references.append(f"receipt_document:{vendor_transaction.receipt_record.document_id}")

    evidence_references.append(f"vendor_engagement_type:{vendor_transaction.vendor_engagement_type.value}")

    if vendor_transaction.misclassification_assessment_record is not None:
        evidence_references.append("misclassification_assessment_record:attached")

        if vendor_transaction.misclassification_assessment_record.document_id is not None:
            evidence_references.append(
                f"misclassification_assessment_document:{vendor_transaction.misclassification_assessment_record.document_id}"
            )

    if vendor_transaction.vendor_payment_details_changed:
        evidence_references.append("vendor_payment_details_changed:true")

    if vendor_transaction.payment_change_verification_record is not None:
        evidence_references.append("payment_change_verification_record:attached")

        if vendor_transaction.payment_change_verification_record.document_id is not None:
            evidence_references.append(
                f"payment_change_verification_document:{vendor_transaction.payment_change_verification_record.document_id}"
            )

    return evidence_references


def _risk_band_for_score(base_risk: float, risk_medium: float, risk_high: float, risk_critical: float) -> RiskBand:
    if base_risk >= risk_critical:
        return RiskBand.CRITICAL
    if base_risk >= risk_high:
        return RiskBand.HIGH
    if base_risk >= risk_medium:
        return RiskBand.MEDIUM
    return RiskBand.LOW


def _evaluate_spend_approval(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate purchase-order spend against single/dual approval thresholds."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    single_approval_amount = escalation_triggers.get("single_approval_amount", 1000)
    dual_approval_amount = escalation_triggers.get("dual_approval_amount", 10000)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    base_risk = 2.0

    if vendor_transaction.amount >= dual_approval_amount:
        base_risk += 4.0
    elif vendor_transaction.amount >= single_approval_amount:
        base_risk += 2.0

    if vendor_transaction.vendor_risk_level == MarketRiskLevel.HIGH:
        base_risk += 2.0

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.5

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)

    requires_approval = vendor_transaction.amount >= single_approval_amount
    requires_dual_approval = vendor_transaction.amount >= dual_approval_amount

    if requires_approval and vendor_transaction.approval_record is None:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Transaction amount {vendor_transaction.amount} meets the approval threshold "
                f"({single_approval_amount}) but no approval record was attached."
            ),
            severity_score=0.6,
            confidence_score=0.9,
            recommended_action="Request approval record from a compliance-authorized approver before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.6,
            triggered_signal_ids=["SIG-MISSING-APPROVAL"],
            signal_rationale=["Spend at or above the approval threshold requires an on-file approval record."],
            escalation_decision="queue_for_approval",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if vendor_transaction.approval_record is not None and vendor_transaction.approval_record.approved is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Approval record on file explicitly denies this spend.",
            severity_score=0.9,
            confidence_score=0.95,
            recommended_action="Block the transaction. Escalate to compliance manager for final disposition.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.9,
            triggered_signal_ids=["SIG-APPROVAL-DENIED"],
            signal_rationale=["The recorded approver denied this spend."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if requires_dual_approval and vendor_transaction.second_approval_record is None:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Transaction amount {vendor_transaction.amount} meets the dual-approval threshold "
                f"({dual_approval_amount}) but only one approval record is on file."
            ),
            severity_score=risk_score,
            confidence_score=0.9,
            recommended_action="Route to a second independent approver before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=risk_band,
            risk_score=risk_score,
            triggered_signal_ids=["SIG-SECOND-APPROVAL-NEEDED"],
            signal_rationale=["High-value spend requires a second, independent approval."],
            escalation_decision="queue_for_second_approval",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if (
        requires_dual_approval
        and vendor_transaction.second_approval_record is not None
        and vendor_transaction.second_approval_record.approved is False
    ):
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Second approval record on file explicitly denies this spend.",
            severity_score=0.9,
            confidence_score=0.95,
            recommended_action="Block the transaction. Escalate to compliance manager for final disposition.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.9,
            triggered_signal_ids=["SIG-APPROVAL-DENIED"],
            signal_rationale=["The second approver denied this spend."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    review_required = risk_band != RiskBand.LOW
    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite approval. Immediate compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance analyst for review before spend is released."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Spend approval evaluated with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_vendor_due_diligence(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate whether a vendor has the required due-diligence screening on file."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    screening_required_above_amount = escalation_triggers.get("screening_required_above_amount", 5000)
    new_vendor_requires_screening = escalation_triggers.get("new_vendor_requires_screening", True)
    high_risk_vendor_requires_screening = escalation_triggers.get("high_risk_vendor_requires_screening", True)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    base_risk = 2.0

    if vendor_transaction.vendor_risk_level == MarketRiskLevel.HIGH:
        base_risk += 3.0
    elif vendor_transaction.vendor_risk_level == MarketRiskLevel.MEDIUM:
        base_risk += 1.0

    if vendor_transaction.new_vendor:
        base_risk += 1.5

    if vendor_transaction.amount >= screening_required_above_amount:
        base_risk += 1.5

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)

    screening_required = (
        (vendor_transaction.new_vendor and new_vendor_requires_screening)
        or (vendor_transaction.vendor_risk_level == MarketRiskLevel.HIGH and high_risk_vendor_requires_screening)
        or vendor_transaction.amount >= screening_required_above_amount
    )

    screening = vendor_transaction.vendor_screening_record

    if screening_required and (screening is None or not screening.completed):
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary="Vendor due-diligence screening is required but not on file or not completed.",
            severity_score=0.65,
            confidence_score=0.9,
            recommended_action="Request completed vendor screening (sanctions/watchlist check) before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.65,
            triggered_signal_ids=["SIG-MISSING-VENDOR-SCREENING"],
            signal_rationale=["Vendor risk profile requires completed due-diligence screening."],
            escalation_decision="queue_for_screening",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if screening is not None and screening.completed and screening.sanctions_check_passed is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Vendor failed sanctions/watchlist screening.",
            severity_score=0.95,
            confidence_score=0.95,
            recommended_action="Block the transaction. Escalate to Legal and compliance manager immediately.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.95,
            triggered_signal_ids=["SIG-SANCTIONS-SCREENING-FAILED"],
            signal_rationale=["Vendor did not clear sanctions/watchlist screening."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    review_required = risk_band != RiskBand.LOW
    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL vendor risk. Immediate compliance manager review required despite passed screening."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance analyst for review before spend is released."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Vendor due-diligence evaluated with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_jurisdiction_due_diligence(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate vendor screening against jurisdiction-specific enhanced due-diligence requirements."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    if vendor_transaction.country_code:
        evidence_references.append(f"jurisdiction:{vendor_transaction.country_code}")

    escalation_triggers = rule.escalation_triggers or {}
    high_risk_country_codes = set(escalation_triggers.get("high_risk_country_codes", []))
    enhanced_dd_required_above_amount = escalation_triggers.get("enhanced_dd_required_above_amount", 5000)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    is_high_risk_jurisdiction = (
        vendor_transaction.country_code is not None and vendor_transaction.country_code in high_risk_country_codes
    )

    if is_high_risk_jurisdiction:
        evidence_references.append("jurisdiction:high_risk")

    base_risk = 2.0

    if is_high_risk_jurisdiction:
        base_risk += 4.0

    if vendor_transaction.amount >= enhanced_dd_required_above_amount:
        base_risk += 1.5

    if vendor_transaction.new_vendor:
        base_risk += 1.0

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)

    enhanced_dd_required = is_high_risk_jurisdiction or vendor_transaction.amount >= enhanced_dd_required_above_amount
    screening = vendor_transaction.vendor_screening_record

    if enhanced_dd_required and (screening is None or not screening.completed):
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Jurisdiction due-diligence evaluation (country: {vendor_transaction.country_code}) requires "
                "completed vendor screening, but none is on file."
            ),
            severity_score=0.65,
            confidence_score=0.88,
            recommended_action="Request completed vendor screening before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.65,
            triggered_signal_ids=["SIG-MISSING-VENDOR-SCREENING"],
            signal_rationale=["Jurisdiction risk profile requires completed vendor screening on file."],
            escalation_decision="queue_for_screening",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if screening is not None and screening.completed and screening.sanctions_check_passed is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Vendor failed sanctions/watchlist screening.",
            severity_score=0.95,
            confidence_score=0.95,
            recommended_action="Block the transaction. Escalate to Legal and compliance manager immediately.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.95,
            triggered_signal_ids=["SIG-SANCTIONS-SCREENING-FAILED"],
            signal_rationale=["Vendor did not clear sanctions/watchlist screening."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if enhanced_dd_required and screening is not None and not screening.enhanced_due_diligence_completed:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Vendor screening is on file but enhanced due diligence is not complete for jurisdiction "
                f"{vendor_transaction.country_code}."
            ),
            severity_score=risk_score,
            confidence_score=0.88,
            recommended_action="Route to compliance manager for enhanced due-diligence sign-off (e.g. local counsel review) before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=risk_band,
            risk_score=risk_score,
            triggered_signal_ids=["SIG-ENHANCED-DD-REQUIRED"],
            signal_rationale=["High-risk jurisdiction or spend level requires enhanced due-diligence sign-off."],
            escalation_decision="queue_for_enhanced_due_diligence",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    review_required = risk_band != RiskBand.LOW
    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL jurisdiction risk despite completed due diligence. Immediate compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance manager for review before spend is released."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Jurisdiction due-diligence evaluated with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_conflict_of_interest(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate a flagged potential conflict of interest between the requestor and the vendor."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    coi_elevated_amount = escalation_triggers.get("coi_elevated_amount", 5000)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    base_risk = 2.0

    if vendor_transaction.potential_conflict_of_interest:
        base_risk += 4.0

    if vendor_transaction.amount >= coi_elevated_amount:
        base_risk += 1.5

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)

    coi_review_required = vendor_transaction.potential_conflict_of_interest
    record = vendor_transaction.conflict_of_interest_record

    if coi_review_required and (record is None or not record.disclosed):
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "A potential conflict of interest was flagged for this vendor but has not been formally disclosed."
            ),
            severity_score=0.65,
            confidence_score=0.9,
            recommended_action="Request a formal conflict-of-interest disclosure before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.65,
            triggered_signal_ids=["SIG-MISSING-COI-DISCLOSURE"],
            signal_rationale=["A flagged potential conflict of interest requires a formal disclosure on file."],
            escalation_decision="queue_for_disclosure",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record is not None and record.disclosed and record.cleared is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Compliance reviewed the disclosed conflict of interest and did not clear it to proceed.",
            severity_score=0.9,
            confidence_score=0.95,
            recommended_action="Block the transaction. Route to an alternate, unconflicted vendor if available.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.9,
            triggered_signal_ids=["SIG-COI-REJECTED"],
            signal_rationale=["Compliance rejected the disclosed conflict of interest."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if coi_review_required and record is not None and record.disclosed and record.cleared is None:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary="Conflict of interest disclosed but a compliance clearance decision is still pending.",
            severity_score=risk_score,
            confidence_score=0.88,
            recommended_action="Route to compliance manager for a clearance decision before spend proceeds.",
            evidence_references=evidence_references,
            risk_band=risk_band,
            risk_score=risk_score,
            triggered_signal_ids=["SIG-COI-REVIEW-PENDING"],
            signal_rationale=["A disclosed conflict of interest requires an explicit compliance clearance decision."],
            escalation_decision="queue_for_coi_clearance",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    review_required = risk_band != RiskBand.LOW
    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite clearance. Immediate compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Cleared, but logged for compliance analyst review given the flagged relationship."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Conflict-of-interest evaluation completed with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_expense_receipt(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate whether an expense has the required receipt documentation on file."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    receipt_required_above_amount = escalation_triggers.get("receipt_required_above_amount", 75)
    receipt_mismatch_tolerance = escalation_triggers.get("receipt_mismatch_tolerance", 0.05)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    receipt_required = vendor_transaction.amount >= receipt_required_above_amount
    record = vendor_transaction.receipt_record

    if receipt_required and (record is None or not record.attached):
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Expense amount {vendor_transaction.amount} meets the receipt threshold "
                f"({receipt_required_above_amount}) but no receipt is attached."
            ),
            severity_score=0.45,
            confidence_score=0.85,
            recommended_action="Request an itemized receipt before the expense is reimbursed or spend proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.MEDIUM,
            risk_score=0.45,
            triggered_signal_ids=["SIG-MISSING-RECEIPT"],
            signal_rationale=["Spend at or above the receipt threshold requires an attached itemized receipt."],
            escalation_decision="queue_for_receipt",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record is not None and record.attached and record.receipt_total is not None:
        mismatch_ratio = abs(record.receipt_total - vendor_transaction.amount) / max(vendor_transaction.amount, 0.01)

        if mismatch_ratio > receipt_mismatch_tolerance:
            return DecisionRecord(
                case_id=vendor_transaction.case_id,
                transaction_id=vendor_transaction.transaction_id,
                decision=DecisionState.HUMAN_REVIEW_REQUIRED,
                evaluated_at=evaluated_at,
                reasoning_summary=(
                    f"Receipt total {record.receipt_total} does not reconcile with the claimed amount "
                    f"{vendor_transaction.amount} within tolerance."
                ),
                severity_score=0.7,
                confidence_score=0.85,
                recommended_action="Route to compliance analyst to reconcile the receipt total against the claimed amount.",
                evidence_references=evidence_references,
                risk_band=RiskBand.HIGH,
                risk_score=0.7,
                triggered_signal_ids=["SIG-RECEIPT-AMOUNT-MISMATCH"],
                signal_rationale=["Attached receipt total does not reconcile with the claimed transaction amount."],
                escalation_decision="queue_for_review",
                escalation_policy_version=VENDOR_ESCALATION_VERSION,
                review_required=True,
                review_status=ReviewStatus.PENDING,
                rule_metadata=rule,
            )

    base_risk = 2.0

    if receipt_required:
        base_risk += 1.0

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.5

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)
    review_required = risk_band != RiskBand.LOW

    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite reconciled receipt. Immediate compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance analyst for review before reimbursement is released."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Expense receipt evaluation completed with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_payment_change_verification(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate whether a vendor payment/banking detail change has been independently
    verified, guarding against business-email-compromise-style payment redirection
    fraud. A transaction with no payment-detail change skips this scrutiny entirely."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    elevated_scrutiny_above_amount = escalation_triggers.get("elevated_scrutiny_above_amount", 5000)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    if not vendor_transaction.vendor_payment_details_changed:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.APPROVED,
            evaluated_at=evaluated_at,
            reasoning_summary="No vendor payment/banking detail change on this transaction; no elevated scrutiny required.",
            severity_score=0.1,
            confidence_score=0.9,
            recommended_action="Approve and log. No further action required.",
            evidence_references=evidence_references,
            risk_band=RiskBand.LOW,
            risk_score=0.1,
            triggered_signal_ids=[],
            signal_rationale=[],
            escalation_decision="auto_close",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=False,
            review_status=ReviewStatus.NOT_REQUIRED,
            rule_metadata=rule,
        )

    record = vendor_transaction.payment_change_verification_record

    if record is None or not record.verification_attempted:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Vendor payment/banking details were changed but no independent verification has been attempted."
            ),
            severity_score=0.65,
            confidence_score=0.88,
            recommended_action="Independently verify the change (e.g. callback to a known phone number) before releasing payment.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.65,
            triggered_signal_ids=["SIG-MISSING-PAYMENT-CHANGE-VERIFICATION"],
            signal_rationale=["A vendor payment/banking detail change requires independent verification before payment proceeds."],
            escalation_decision="queue_for_verification",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record.verified is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Verification of the vendor payment/banking detail change failed — possible fraud.",
            severity_score=0.95,
            confidence_score=0.9,
            recommended_action="Block the payment. Escalate to Finance and Legal immediately as a suspected fraud incident.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.95,
            triggered_signal_ids=["SIG-PAYMENT-CHANGE-VERIFICATION-FAILED"],
            signal_rationale=["Independent verification could not confirm the payment/banking detail change is legitimate."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record.verified is None:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary="Verification of the vendor payment/banking detail change was attempted but is not yet confirmed.",
            severity_score=0.6,
            confidence_score=0.82,
            recommended_action="Route to compliance manager for a verification determination before payment proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.6,
            triggered_signal_ids=["SIG-PAYMENT-CHANGE-VERIFICATION-PENDING"],
            signal_rationale=["A payment/banking detail change verification determination has not yet been made."],
            escalation_decision="queue_for_determination",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    # record.verified is True: still carries an elevated baseline risk relative to a
    # transaction with no payment-detail change, mirroring the same "cleared but still
    # logged" precedent used for a cleared conflict of interest or a confirmed-contractor
    # part-time engagement.
    base_risk = 2.0 + 4.0

    if vendor_transaction.amount >= elevated_scrutiny_above_amount:
        base_risk += 1.5

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)
    review_required = risk_band != RiskBand.LOW

    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite verified change. Immediate Finance and compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to Finance for confirmation before payment is released."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Payment change verification evaluated with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.85,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_gifts_and_hospitality(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate gifts, hospitality, or entertainment given to or received from a
    vendor against pre-approval requirements, with a stricter (zero-amount) threshold
    when the counterparty is a government official."""
    evidence_references = _build_base_evidence_references(vendor_transaction)
    evidence_references.append(f"gift_recipient_type:{vendor_transaction.gift_recipient_type.value}")

    escalation_triggers = rule.escalation_triggers or {}
    standard_approval_threshold = escalation_triggers.get("standard_approval_threshold", 150)
    government_official_approval_threshold = escalation_triggers.get("government_official_approval_threshold", 0)
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    is_government_official = vendor_transaction.gift_recipient_type == GiftRecipientType.GOVERNMENT_OFFICIAL

    base_risk = 2.0

    if is_government_official:
        base_risk += 4.0

    if vendor_transaction.amount >= standard_approval_threshold:
        base_risk += 1.5

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)

    requires_approval = (
        vendor_transaction.amount >= standard_approval_threshold
        or (is_government_official and vendor_transaction.amount >= government_official_approval_threshold)
    )

    if requires_approval and vendor_transaction.approval_record is None:
        if is_government_official:
            return DecisionRecord(
                case_id=vendor_transaction.case_id,
                transaction_id=vendor_transaction.transaction_id,
                decision=DecisionState.INSUFFICIENT_EVIDENCE,
                evaluated_at=evaluated_at,
                reasoning_summary=(
                    "Gift, hospitality, or entertainment involving a government official requires "
                    "pre-approval regardless of amount, but no approval record is on file."
                ),
                severity_score=0.85,
                confidence_score=0.9,
                recommended_action="Request compliance manager pre-approval before this gift/hospitality proceeds.",
                evidence_references=evidence_references,
                risk_band=RiskBand.CRITICAL,
                risk_score=0.85,
                triggered_signal_ids=["SIG-MISSING-GOV-OFFICIAL-GIFT-APPROVAL"],
                signal_rationale=["Gifts/hospitality involving a government official require pre-approval at any amount."],
                escalation_decision="queue_for_approval",
                escalation_policy_version=VENDOR_ESCALATION_VERSION,
                review_required=True,
                review_status=ReviewStatus.PENDING,
                rule_metadata=rule,
            )

        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                f"Gift/hospitality amount {vendor_transaction.amount} meets the approval threshold "
                f"({standard_approval_threshold}) but no approval record is on file."
            ),
            severity_score=0.6,
            confidence_score=0.88,
            recommended_action="Request pre-approval before this gift/hospitality proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.6,
            triggered_signal_ids=["SIG-MISSING-GIFT-APPROVAL"],
            signal_rationale=["Gift/hospitality spend at or above the approval threshold requires an on-file approval record."],
            escalation_decision="queue_for_approval",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if vendor_transaction.approval_record is not None and vendor_transaction.approval_record.approved is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.BLOCKED,
            evaluated_at=evaluated_at,
            reasoning_summary="Approval record on file explicitly denies this gift/hospitality/entertainment spend.",
            severity_score=0.9,
            confidence_score=0.95,
            recommended_action="Block the transaction. Escalate to Legal for anti-corruption review.",
            evidence_references=evidence_references,
            risk_band=RiskBand.CRITICAL,
            risk_score=0.9,
            triggered_signal_ids=["SIG-GIFT-APPROVAL-DENIED"],
            signal_rationale=["The recorded approver denied this gift/hospitality/entertainment spend."],
            escalation_decision="mandatory_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    review_required = risk_band != RiskBand.LOW
    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite approval. Immediate Legal review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance analyst for review."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Gifts/hospitality evaluation completed with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_part_time_contract_classification(
    vendor_transaction: VendorTransaction,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate part-time/temporary contract vendor engagements for worker-
    misclassification risk. A standard vendor engagement skips this scrutiny
    entirely and clears at low risk."""
    evidence_references = _build_base_evidence_references(vendor_transaction)

    escalation_triggers = rule.escalation_triggers or {}
    review_required_above_hours = escalation_triggers.get(
        "misclassification_review_required_above_hours_per_week", 20
    )
    risk_medium = escalation_triggers.get("risk_score_medium", 4)
    risk_high = escalation_triggers.get("risk_score_high", 6)
    risk_critical = escalation_triggers.get("risk_score_critical", 8)

    elevated_engagement = vendor_transaction.vendor_engagement_type in (
        VendorEngagementType.PART_TIME_CONTRACT,
        VendorEngagementType.TEMPORARY_STAFFING,
    )

    if not elevated_engagement:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.APPROVED,
            evaluated_at=evaluated_at,
            reasoning_summary="Standard vendor engagement; no elevated worker-classification scrutiny required.",
            severity_score=0.1,
            confidence_score=0.9,
            recommended_action="Approve and log. No further action required.",
            evidence_references=evidence_references,
            risk_band=RiskBand.LOW,
            risk_score=0.1,
            triggered_signal_ids=[],
            signal_rationale=[],
            escalation_decision="auto_close",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=False,
            review_status=ReviewStatus.NOT_REQUIRED,
            rule_metadata=rule,
        )

    record = vendor_transaction.misclassification_assessment_record

    if record is None or not record.completed:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Part-time/temporary contract engagement requires a completed worker-classification "
                "risk assessment, but none is on file."
            ),
            severity_score=0.6,
            confidence_score=0.85,
            recommended_action="Request a completed worker-classification risk assessment before this engagement proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.6,
            triggered_signal_ids=["SIG-MISSING-MISCLASSIFICATION-ASSESSMENT"],
            signal_rationale=["Part-time/temporary contract engagements require a documented worker-classification assessment."],
            escalation_decision="queue_for_assessment",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record.classification_confirmed_as_contractor is False:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary=(
                "Assessment indicates this engagement may function as part-time employment rather than "
                "an independent-contractor relationship."
            ),
            severity_score=0.75,
            confidence_score=0.85,
            recommended_action="Route to Legal and HR for a reclassification review before this engagement continues.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.75,
            triggered_signal_ids=["SIG-POSSIBLE-WORKER-MISCLASSIFICATION"],
            signal_rationale=[
                "Worker-classification assessment suggests the engagement resembles employment, not an independent-contractor vendor relationship."
            ],
            escalation_decision="queue_for_reclassification_review",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    if record.classification_confirmed_as_contractor is None:
        return DecisionRecord(
            case_id=vendor_transaction.case_id,
            transaction_id=vendor_transaction.transaction_id,
            decision=DecisionState.HUMAN_REVIEW_REQUIRED,
            evaluated_at=evaluated_at,
            reasoning_summary="Worker-classification assessment is on file but a determination is still pending.",
            severity_score=0.55,
            confidence_score=0.8,
            recommended_action="Route to compliance manager for a classification determination before this engagement proceeds.",
            evidence_references=evidence_references,
            risk_band=RiskBand.MEDIUM,
            risk_score=0.55,
            triggered_signal_ids=["SIG-MISCLASSIFICATION-DETERMINATION-PENDING"],
            signal_rationale=["A worker-classification determination has not yet been made."],
            escalation_decision="queue_for_determination",
            escalation_policy_version=VENDOR_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    # classification_confirmed_as_contractor is True: still carries an elevated
    # baseline risk relative to a standard vendor, mirroring how a cleared
    # conflict-of-interest case still routes to review rather than auto-closing.
    base_risk = 2.0 + 4.0

    if (record.hours_per_week or 0) >= review_required_above_hours:
        base_risk += 1.5

    if vendor_transaction.prior_flagged_transactions_12m >= 1:
        base_risk += 1.0

    base_risk = min(base_risk, 10.0)
    risk_score = base_risk / 10.0
    risk_band = _risk_band_for_score(base_risk, risk_medium, risk_high, risk_critical)
    review_required = risk_band != RiskBand.LOW

    if risk_band == RiskBand.CRITICAL:
        action = "CRITICAL risk despite confirmed contractor classification. Immediate compliance manager review required."
    elif risk_band == RiskBand.HIGH:
        action = "Route to compliance manager for periodic reclassification review."
    elif risk_band == RiskBand.MEDIUM:
        action = "Log for standard compliance review."
    else:
        action = "Approve and log. No further action required."

    return DecisionRecord(
        case_id=vendor_transaction.case_id,
        transaction_id=vendor_transaction.transaction_id,
        decision=DecisionState.APPROVED,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Part-time/temporary contract engagement evaluated with risk score {base_risk:.1f}/10.",
        severity_score=risk_score,
        confidence_score=0.85,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=risk_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision="auto_close" if not review_required else "queue_for_review",
        escalation_policy_version=VENDOR_ESCALATION_VERSION,
        review_required=review_required,
        review_status=ReviewStatus.PENDING if review_required else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _determine_escalation_recipients(rule: RuleMetadata, risk_band: RiskBand) -> list[NotificationRecipient]:
    """Look up which stakeholder groups to notify for this risk band, per the rule's
    versioned notification policy. An unconfigured rule or band notifies no one rather
    than guessing, consistent with the same deterministic, policy-traceable approach
    used for every other escalation trigger."""
    notification_config = (rule.escalation_triggers or {}).get("notification_recipients", {})
    configured_recipients = notification_config.get(risk_band.value, [])
    return [NotificationRecipient(recipient) for recipient in configured_recipients]


def evaluate_vendor_case(vendor_transaction: VendorTransaction) -> DecisionRecord:
    """Evaluate a vendor transaction case against the applicable procurement rule."""
    rule = load_rule(vendor_transaction.control_id)
    evaluated_at = datetime.now(UTC).isoformat()

    if rule.control_domain == "procurement":
        if "PAYMENT-CHANGE" in rule.control_id:
            decision_record = _evaluate_payment_change_verification(vendor_transaction, rule, evaluated_at)
        elif "GIFTS-HOSPITALITY" in rule.control_id:
            decision_record = _evaluate_gifts_and_hospitality(vendor_transaction, rule, evaluated_at)
        elif "PART-TIME" in rule.control_id:
            decision_record = _evaluate_part_time_contract_classification(vendor_transaction, rule, evaluated_at)
        elif "RECEIPT" in rule.control_id:
            decision_record = _evaluate_expense_receipt(vendor_transaction, rule, evaluated_at)
        elif "COI" in rule.control_id:
            decision_record = _evaluate_conflict_of_interest(vendor_transaction, rule, evaluated_at)
        elif "INTL" in rule.control_id:
            decision_record = _evaluate_jurisdiction_due_diligence(vendor_transaction, rule, evaluated_at)
        elif "DUEDILIGENCE" in rule.control_id:
            decision_record = _evaluate_vendor_due_diligence(vendor_transaction, rule, evaluated_at)
        elif "SPEND-APPROVAL" in rule.control_id:
            decision_record = _evaluate_spend_approval(vendor_transaction, rule, evaluated_at)
        else:
            # Default handler for unknown procurement controls
            decision_record = _evaluate_spend_approval(vendor_transaction, rule, evaluated_at)

        escalation_recipients = _determine_escalation_recipients(rule, decision_record.risk_band)
        return decision_record.model_copy(update={"escalation_recipients": escalation_recipients})

    raise ValueError(f"Unsupported control_domain: {rule.control_domain}")


def calculate_review_queue_metrics(decisions: list[DecisionRecord], sla_target_hours: float = DEFAULT_SLA_HOURS) -> ReviewQueueMetrics:
    """Calculate metrics for the active review queue."""
    active_decisions = [decision for decision in decisions if decision.review_required]
    zero_band_counts = {band: 0 for band in RiskBand}

    if not active_decisions:
        return ReviewQueueMetrics(
            active_review_count=0,
            pending_count=0,
            assigned_count=0,
            in_review_count=0,
            reopened_count=0,
            breached_sla_count=0,
            active_by_risk_band=zero_band_counts,
            breached_sla_by_risk_band=zero_band_counts,
            average_queue_age_hours=0.0,
            oldest_queue_age_hours=0.0,
            sla_target_hours=sla_target_hours,
        )

    now = datetime.now(UTC)
    queue_ages_hours: list[float] = []
    breached_sla_count = 0
    active_by_risk_band = {band: 0 for band in RiskBand}
    breached_sla_by_risk_band = {band: 0 for band in RiskBand}

    for decision in active_decisions:
        started_at = datetime.fromisoformat(decision.evaluated_at)
        age_hours = (now - started_at).total_seconds() / 3600
        queue_ages_hours.append(age_hours)
        active_by_risk_band[decision.risk_band] += 1

        if age_hours > sla_target_hours:
            breached_sla_count += 1
            breached_sla_by_risk_band[decision.risk_band] += 1

    return ReviewQueueMetrics(
        active_review_count=len(active_decisions),
        pending_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.PENDING),
        assigned_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.ASSIGNED),
        in_review_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.IN_REVIEW),
        reopened_count=sum(1 for decision in active_decisions if decision.review_status == ReviewStatus.REOPENED),
        breached_sla_count=breached_sla_count,
        active_by_risk_band=active_by_risk_band,
        breached_sla_by_risk_band=breached_sla_by_risk_band,
        average_queue_age_hours=round(sum(queue_ages_hours) / len(queue_ages_hours), 2),
        oldest_queue_age_hours=round(max(queue_ages_hours), 2),
        sla_target_hours=sla_target_hours,
    )


def calculate_dashboard_summary(
    decisions: list[DecisionRecord],
    sla_target_hours: float = DEFAULT_SLA_HOURS,
) -> DashboardSummary:
    """Aggregate decisions into a governance dashboard: per-control breakdown, signal
    frequency, risk-band distribution, and the active review queue snapshot."""
    control_totals: dict[str, dict] = {}

    for rule in load_rules():
        control_totals[rule.control_id] = {
            "policy_name": rule.policy_name,
            "total_decisions": 0,
            "approved_count": 0,
            "blocked_count": 0,
            "insufficient_evidence_count": 0,
            "human_review_required_count": 0,
            "active_review_count": 0,
        }

    decision_count_by_risk_band = {band: 0 for band in RiskBand}
    signal_counts: dict[str, int] = {}
    pending_notifications_by_recipient = {recipient: 0 for recipient in NotificationRecipient}

    for decision in decisions:
        control_id = decision.rule_metadata.control_id
        totals = control_totals.setdefault(
            control_id,
            {
                "policy_name": decision.rule_metadata.policy_name,
                "total_decisions": 0,
                "approved_count": 0,
                "blocked_count": 0,
                "insufficient_evidence_count": 0,
                "human_review_required_count": 0,
                "active_review_count": 0,
            },
        )
        totals["total_decisions"] += 1

        if decision.decision == DecisionState.APPROVED:
            totals["approved_count"] += 1
        elif decision.decision == DecisionState.BLOCKED:
            totals["blocked_count"] += 1
        elif decision.decision == DecisionState.INSUFFICIENT_EVIDENCE:
            totals["insufficient_evidence_count"] += 1
        elif decision.decision == DecisionState.HUMAN_REVIEW_REQUIRED:
            totals["human_review_required_count"] += 1

        if decision.review_required:
            totals["active_review_count"] += 1

        decision_count_by_risk_band[decision.risk_band] += 1

        for signal_id in decision.triggered_signal_ids:
            signal_counts[signal_id] = signal_counts.get(signal_id, 0) + 1

        if decision.review_required:
            for recipient in decision.escalation_recipients:
                pending_notifications_by_recipient[recipient] += 1

    controls = [
        ControlSummary(control_id=control_id, **totals) for control_id, totals in sorted(control_totals.items())
    ]

    top_triggered_signals = sorted(
        (SignalFrequency(signal_id=signal_id, count=count) for signal_id, count in signal_counts.items()),
        key=lambda signal: signal.count,
        reverse=True,
    )

    return DashboardSummary(
        generated_at=datetime.now(UTC).isoformat(),
        total_decisions=len(decisions),
        total_active_reviews=sum(1 for decision in decisions if decision.review_required),
        total_blocked=sum(1 for decision in decisions if decision.decision == DecisionState.BLOCKED),
        total_insufficient_evidence=sum(
            1 for decision in decisions if decision.decision == DecisionState.INSUFFICIENT_EVIDENCE
        ),
        decision_count_by_risk_band=decision_count_by_risk_band,
        controls=controls,
        top_triggered_signals=top_triggered_signals,
        pending_notifications_by_recipient=pending_notifications_by_recipient,
        queue_metrics=calculate_review_queue_metrics(decisions, sla_target_hours),
    )
