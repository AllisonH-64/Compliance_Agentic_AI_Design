import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import (
    DEFAULT_CONTROL_ID,
    DecisionRecord,
    DecisionState,
    IncidentCategory,
    InvolvedPartyRole,
    RiskBand,
    ReviewQueueMetrics,
    ReviewStatus,
    RuleMetadata,
    IncidentCase,
)


RULES_DIR = Path(__file__).resolve().parents[1] / "data" / "rules"
DEFAULT_SLA_HOURS = 24.0
CONDUCT_ESCALATION_VERSION = "conduct-escalation-v1"


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


def _build_base_evidence_references(incident_case: IncidentCase) -> list[str]:
    evidence_references = [
        f"incident:{incident_case.incident_id}",
        f"control:{incident_case.control_id}",
    ]

    if incident_case.incident_report is not None:
        evidence_references.append("incident_report:attached")

        if incident_case.incident_report.document_id is not None:
            evidence_references.append(f"incident_report_document:{incident_case.incident_report.document_id}")

    if incident_case.evidence_record is not None:
        evidence_references.append("evidence_record:attached")

        if incident_case.evidence_record.document_id is not None:
            evidence_references.append(f"evidence_document:{incident_case.evidence_record.document_id}")

    return evidence_references


def _evaluate_harassment_bullying_incident(
    incident_case: IncidentCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate harassment/bullying incidents based on severity and evidence."""
    evidence_references = _build_base_evidence_references(incident_case)

    # Extract escalation triggers from rule
    escalation_triggers = rule.escalation_triggers or {}
    severity_medium = escalation_triggers.get("severity_score_medium", 4)
    severity_high = escalation_triggers.get("severity_score_high", 7)
    severity_critical = escalation_triggers.get("severity_score_critical", 9)

    # Calculate severity based on incident description length and protected characteristics
    base_severity = 3.0
    
    if len(incident_case.incident_description) > 500:
        base_severity += 2.0
    elif len(incident_case.incident_description) > 200:
        base_severity += 1.0

    if incident_case.protected_characteristic_mentioned:
        base_severity += 2.0

    if incident_case.prior_complaints_12m >= 2:
        base_severity += 2.0

    if incident_case.involved_parties_count > 2:
        base_severity += 1.0

    # Cap severity at 10
    base_severity = min(base_severity, 10.0)
    severity_score = base_severity / 10.0  # Normalize to 0-1
    
    # Missing incident report is a critical gap
    if incident_case.incident_report is None:
        return DecisionRecord(
            case_id=incident_case.case_id,
            incident_id=incident_case.incident_id,
            decision=DecisionState.INSUFFICIENT_EVIDENCE,
            evaluated_at=evaluated_at,
            reasoning_summary="Incident reported but no formal incident report document was attached.",
            severity_score=0.7,
            confidence_score=0.85,
            recommended_action="Request formal incident report document and route to investigator.",
            evidence_references=evidence_references,
            risk_band=RiskBand.HIGH,
            risk_score=0.7,
            triggered_signal_ids=["SIG-MISSING-INCIDENT-REPORT"],
            signal_rationale=["Incident report documentation is required for investigation."],
            escalation_decision="investigation_required",
            escalation_policy_version=CONDUCT_ESCALATION_VERSION,
            review_required=True,
            review_status=ReviewStatus.PENDING,
            rule_metadata=rule,
        )

    # Determine risk band and escalation based on severity
    if base_severity >= severity_critical:
        risk_band = RiskBand.CRITICAL
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "IMMEDIATE escalation to HR, Legal, and senior management. Urgent investigation required."
        escalation = "investigation_required"
    elif base_severity >= severity_high:
        risk_band = RiskBand.HIGH
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to investigation team immediately."
        escalation = "investigation_required"
    elif base_severity >= severity_medium:
        risk_band = RiskBand.MEDIUM
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to investigation team for standard investigation."
        escalation = "investigation_required"
    else:
        risk_band = RiskBand.LOW
        decision = DecisionState.CLEARED
        action = "Log incident and monitor for pattern. No immediate action required."
        escalation = "monitor_only"

    return DecisionRecord(
        case_id=incident_case.case_id,
        incident_id=incident_case.incident_id,
        decision=decision,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Harassment/bullying incident evaluated with severity score {base_severity:.1f}/10.",
        severity_score=severity_score,
        confidence_score=0.88,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=severity_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision=escalation,
        escalation_policy_version=CONDUCT_ESCALATION_VERSION,
        review_required=(decision != DecisionState.CLEARED),
        review_status=ReviewStatus.PENDING if decision != DecisionState.CLEARED else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_discrimination_incident(
    incident_case: IncidentCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate discrimination incidents with heightened scrutiny."""
    evidence_references = _build_base_evidence_references(incident_case)

    escalation_triggers = rule.escalation_triggers or {}
    severity_medium = escalation_triggers.get("severity_score_medium", 4)
    severity_high = escalation_triggers.get("severity_score_high", 6)
    severity_critical = escalation_triggers.get("severity_score_critical", 8)

    # Discrimination allegations are treated seriously
    base_severity = 5.0  # Higher baseline
    
    if incident_case.protected_characteristic_mentioned:
        base_severity = max(base_severity, 7.0)
        evidence_references.append("protected_characteristic:mentioned")

    if len(incident_case.incident_description) > 300:
        base_severity += 1.5

    if incident_case.involved_parties_count > 1:
        base_severity += 1.0

    base_severity = min(base_severity, 10.0)
    severity_score = base_severity / 10.0

    # Discrimination claims require escalation to Legal
    if base_severity >= severity_critical:
        risk_band = RiskBand.CRITICAL
        decision = DecisionState.POLICY_VIOLATION_CONFIRMED
        action = "IMMEDIATE escalation to HR, Legal, and C-suite. Formal investigation + legal review required."
        escalation = "investigation_required"
    elif base_severity >= severity_high:
        risk_band = RiskBand.HIGH
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Escalate to Legal and HR immediately for investigation."
        escalation = "investigation_required"
    else:
        risk_band = RiskBand.MEDIUM
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to HR for investigation."
        escalation = "investigation_required"

    return DecisionRecord(
        case_id=incident_case.case_id,
        incident_id=incident_case.incident_id,
        decision=decision,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Discrimination incident evaluated with severity score {base_severity:.1f}/10. Protected characteristics: {incident_case.protected_characteristic_mentioned}",
        severity_score=severity_score,
        confidence_score=0.92,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=severity_score,
        triggered_signal_ids=["SIG-DISCRIMINATION"] if incident_case.protected_characteristic_mentioned else [],
        signal_rationale=["Potential discrimination based on protected characteristic."] if incident_case.protected_characteristic_mentioned else [],
        escalation_decision=escalation,
        escalation_policy_version=CONDUCT_ESCALATION_VERSION,
        review_required=True,
        review_status=ReviewStatus.PENDING,
        rule_metadata=rule,
    )


def _evaluate_client_treatment_incident(
    incident_case: IncidentCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate client treatment and conflict of interest incidents."""
    evidence_references = _build_base_evidence_references(incident_case)

    escalation_triggers = rule.escalation_triggers or {}
    severity_medium = escalation_triggers.get("severity_score_medium", 4)
    severity_high = escalation_triggers.get("severity_score_high", 6)
    severity_critical = escalation_triggers.get("severity_score_critical", 8)

    base_severity = 2.0
    
    if len(incident_case.incident_description) > 400:
        base_severity += 2.0
    elif len(incident_case.incident_description) > 200:
        base_severity += 1.0

    # Client relationship incidents are important for business reputation
    if incident_case.involved_party_role == InvolvedPartyRole.CLIENT:
        base_severity += 2.5

    if incident_case.prior_complaints_12m >= 1:
        base_severity += 1.5

    base_severity = min(base_severity, 10.0)
    severity_score = base_severity / 10.0

    if base_severity >= severity_critical:
        risk_band = RiskBand.CRITICAL
        decision = DecisionState.POLICY_VIOLATION_CONFIRMED
        action = "CRITICAL escalation - potential client relationship damage. Business leadership + Legal review required."
        escalation = "investigation_required"
    elif base_severity >= severity_high:
        risk_band = RiskBand.HIGH
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to business relationship manager and compliance team for investigation."
        escalation = "investigation_required"
    elif base_severity >= severity_medium:
        risk_band = RiskBand.MEDIUM
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to compliance analyst for investigation."
        escalation = "investigation_required"
    else:
        risk_band = RiskBand.LOW
        decision = DecisionState.CLEARED
        action = "Log as low-severity client interaction issue. Monitor for patterns."
        escalation = "monitor_only"

    return DecisionRecord(
        case_id=incident_case.case_id,
        incident_id=incident_case.incident_id,
        decision=decision,
        evaluated_at=evaluated_at,
        reasoning_summary=f"Client treatment incident evaluated with severity score {base_severity:.1f}/10.",
        severity_score=severity_score,
        confidence_score=0.86,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=severity_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision=escalation,
        escalation_policy_version=CONDUCT_ESCALATION_VERSION,
        review_required=(decision != DecisionState.CLEARED),
        review_status=ReviewStatus.PENDING if decision != DecisionState.CLEARED else ReviewStatus.NOT_REQUIRED,
        rule_metadata=rule,
    )


def _evaluate_international_governance_incident(
    incident_case: IncidentCase,
    rule: RuleMetadata,
    evaluated_at: str,
) -> DecisionRecord:
    """Evaluate incidents involving international employment law and regulatory compliance."""
    evidence_references = _build_base_evidence_references(incident_case)
    
    if incident_case.country_code:
        evidence_references.append(f"jurisdiction:{incident_case.country_code}")

    escalation_triggers = rule.escalation_triggers or {}
    severity_medium = escalation_triggers.get("severity_score_medium", 4)
    severity_high = escalation_triggers.get("severity_score_high", 6)
    severity_critical = escalation_triggers.get("severity_score_critical", 8)

    base_severity = 3.0
    
    if incident_case.protected_characteristic_mentioned:
        base_severity += 3.0
        evidence_references.append("international:protected_char")

    if len(incident_case.incident_description) > 300:
        base_severity += 1.5

    # International governance issues often require legal expertise
    if incident_case.jurisdiction_risk_level and incident_case.jurisdiction_risk_level.value == "high":
        base_severity += 2.0
        evidence_references.append("international:high_risk_jurisdiction")

    base_severity = min(base_severity, 10.0)
    severity_score = base_severity / 10.0

    if base_severity >= severity_critical:
        risk_band = RiskBand.CRITICAL
        decision = DecisionState.POLICY_VIOLATION_CONFIRMED
        action = "URGENT escalation to Legal and International Compliance. Potential regulatory authority notification required."
        escalation = "investigation_required"
    elif base_severity >= severity_high:
        risk_band = RiskBand.HIGH
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Escalate to International Compliance and Local Legal Counsel immediately."
        escalation = "investigation_required"
    elif base_severity >= severity_medium:
        risk_band = RiskBand.MEDIUM
        decision = DecisionState.INVESTIGATION_REQUIRED
        action = "Route to International Compliance team for jurisdiction-specific investigation."
        escalation = "investigation_required"
    else:
        risk_band = RiskBand.LOW
        decision = DecisionState.CLEARED
        action = "Log incident and monitor for international regulatory updates."
        escalation = "monitor_only"

    return DecisionRecord(
        case_id=incident_case.case_id,
        incident_id=incident_case.incident_id,
        decision=decision,
        evaluated_at=evaluated_at,
        reasoning_summary=f"International governance incident (jurisdiction: {incident_case.country_code}) evaluated with severity score {base_severity:.1f}/10.",
        severity_score=severity_score,
        confidence_score=0.84,
        recommended_action=action,
        evidence_references=evidence_references,
        risk_band=risk_band,
        risk_score=severity_score,
        triggered_signal_ids=[],
        signal_rationale=[],
        escalation_decision=escalation,
        escalation_policy_version=CONDUCT_ESCALATION_VERSION,
        review_required=True,
        review_status=ReviewStatus.PENDING,
        rule_metadata=rule,
    )


def evaluate_incident_case(incident_case: IncidentCase) -> DecisionRecord:
    """Evaluate a conduct incident case against the applicable rule."""
    rule = load_rule(incident_case.control_id)
    evaluated_at = datetime.now(UTC).isoformat()

    if rule.control_domain == "employee_conduct":
        # Route to appropriate evaluator based on control ID
        if "HARASSMENT" in rule.control_id:
            return _evaluate_harassment_bullying_incident(incident_case, rule, evaluated_at)
        elif "DISCRIMINATION" in rule.control_id:
            return _evaluate_discrimination_incident(incident_case, rule, evaluated_at)
        elif "CLIENT" in rule.control_id:
            return _evaluate_client_treatment_incident(incident_case, rule, evaluated_at)
        elif "INTL" in rule.control_id:
            return _evaluate_international_governance_incident(incident_case, rule, evaluated_at)
        else:
            # Default handler for unknown conduct controls
            return _evaluate_harassment_bullying_incident(incident_case, rule, evaluated_at)

    raise ValueError(f"Unsupported control_domain: {rule.control_domain}")


def calculate_review_queue_metrics(decisions: list[DecisionRecord], sla_target_hours: float = DEFAULT_SLA_HOURS) -> ReviewQueueMetrics:
    """Calculate metrics for the active investigation queue."""
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
