from enum import Enum

from pydantic import BaseModel, Field


DEFAULT_CONTROL_ID = "CONDUCT-HARASSMENT-001"


class DecisionState(str, Enum):
    POLICY_VIOLATION_CONFIRMED = "policy_violation_confirmed"
    CLEARED = "cleared"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVESTIGATION_REQUIRED = "investigation_required"


class ReviewerOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    REOPENED = "reopened"
    COMPLETED = "completed"


class UserRole(str, Enum):
    EMPLOYEE = "employee"
    COMPLIANCE_ANALYST = "compliance_analyst"
    COMPLIANCE_MANAGER = "compliance_manager"
    AUDITOR = "auditor"


class InvolvedPartyRole(str, Enum):
    RESPONDENT = "respondent"
    COMPLAINANT = "complainant"
    WITNESS = "witness"
    MANAGER = "manager"
    CLIENT = "client"
    VENDOR = "vendor"
    UNKNOWN = "unknown"


class MarketRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentCategory(str, Enum):
    HARASSMENT_BULLYING = "harassment_bullying"
    DISCRIMINATION = "discrimination"
    CLIENT_TREATMENT = "client_treatment"
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    INTERNATIONAL_GOVERNANCE = "international_governance"
    OTHER = "other"


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReopenReason(str, Enum):
    NEW_EVIDENCE = "new_evidence"
    POLICY_UPDATE = "policy_update"
    APPEAL = "appeal"
    AUDIT_FOLLOWUP = "audit_followup"
    OTHER = "other"


class IncidentReport(BaseModel):
    attached: bool = Field(..., description="Whether an incident report was filed")
    document_id: str | None = Field(default=None, description="Identifier for the incident report document")


class EvidenceRecord(BaseModel):
    attached: bool = Field(..., description="Whether supporting evidence (witness statements, communications, etc.) was attached")
    document_id: str | None = Field(default=None, description="Identifier for the evidence document")


class IncidentCase(BaseModel):
    case_id: str = Field(..., description="Unique identifier for the compliance case")
    incident_id: str = Field(..., description="Unique identifier for the incident report")
    control_id: str = Field(
        default=DEFAULT_CONTROL_ID,
        description="Identifier for the rule control to evaluate against",
    )
    respondent_name: str = Field(..., description="Name or identifier of the respondent (subject of the incident)")
    complainant_name: str | None = Field(
        default=None,
        description="Name or identifier of the complainant (person filing the incident)"
    )
    submitter_role: str = Field(..., description="Role of the person submitting the incident")
    incident_report: IncidentReport | None = Field(
        default=None,
        description="Incident report evidence attached to the case",
    )
    evidence_record: EvidenceRecord | None = Field(
        default=None,
        description="Supporting evidence (witness statements, communications) attached when required by the selected control",
    )
    involved_party_role: InvolvedPartyRole | None = Field(
        default=None,
        description="Classification of the respondent for risk scoring",
    )
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO country code where the incident occurred",
    )
    jurisdiction_risk_level: MarketRiskLevel | None = Field(
        default=None,
        description="Compliance-managed jurisdiction risk tier",
    )
    incident_description: str = Field(..., description="Detailed description of the incident")
    incident_date: str | None = Field(
        default=None,
        description="Date when the incident occurred (ISO 8601 format)"
    )
    prior_complaints_12m: int = Field(
        default=0,
        ge=0,
        description="Count of prior complaints involving the same respondent in the last 12 months",
    )
    escalation_reference: str | None = Field(
        default=None,
        description="Optional escalation or prior investigation identifier",
    )
    incident_category: IncidentCategory | None = Field(
        default=None,
        description="Category of the incident for routing and rule evaluation",
    )
    involved_parties_count: int = Field(
        default=1,
        ge=1,
        description="Number of individuals directly involved in the incident",
    )
    protected_characteristic_mentioned: bool = Field(
        default=False,
        description="Whether the incident involves protected characteristics (age, gender, race, disability, etc.)"
    )


class RuleMetadata(BaseModel):
    control_id: str
    control_domain: str
    policy_name: str
    policy_version: str
    description: str
    severity_threshold: float | None = Field(default=None, description="Minimum severity score to trigger action")
    required_evidence: list[str]
    required_investigator_role: str | None = None
    international_applicability: list[str] = Field(default_factory=lambda: ["ALL"])
    escalation_triggers: dict | None = Field(default=None, description="Conditions that trigger escalation")


class DecisionRecord(BaseModel):
    case_id: str
    incident_id: str
    decision: DecisionState
    evaluated_at: str
    reasoning_summary: str
    severity_score: float = Field(..., ge=0, le=1)
    confidence_score: float = Field(..., ge=0, le=1)
    recommended_action: str
    evidence_references: list[str]
    risk_band: RiskBand = RiskBand.LOW
    risk_score: float = Field(default=0.0, ge=0, le=1)
    triggered_signal_ids: list[str] = Field(default_factory=list)
    signal_rationale: list[str] = Field(default_factory=list)
    escalation_decision: str = "investigation_required"
    escalation_policy_version: str = "conduct-escalation-v1"
    review_cycle_id: int = Field(default=1, ge=1)
    reopen_reason: ReopenReason | None = None
    review_required: bool
    review_status: ReviewStatus
    assigned_reviewer_id: str | None = None
    assigned_at: str | None = None
    review_started_at: str | None = None
    final_reviewer_outcome: ReviewerOutcome | None = None
    final_reviewed_at: str | None = None
    rule_metadata: RuleMetadata


class ReviewAssignment(BaseModel):
    reviewer_id: str = Field(..., description="Identifier for the assigned reviewer")


class ReviewStart(BaseModel):
    reviewer_id: str = Field(..., description="Identifier for the reviewer starting work")


class ReviewSubmission(BaseModel):
    reviewer_id: str = Field(..., description="Identifier for the reviewer")
    outcome: ReviewerOutcome = Field(..., description="Reviewer's final adjudication")
    final_decision: DecisionState = Field(..., description="Final compliance decision after human review")
    notes: str = Field(..., min_length=1, description="Reviewer notes explaining the decision")


class ReviewReopen(BaseModel):
    reason: ReopenReason = Field(..., description="Reason for reopening a completed review cycle")
    notes: str = Field(..., min_length=1, description="Context for why the case is being reopened")


class ReviewRecord(BaseModel):
    case_id: str
    reviewer_id: str
    outcome: ReviewerOutcome
    final_decision: DecisionState | None = None
    notes: str
    reviewed_at: str


class ReviewQueueItem(BaseModel):
    decision_record: DecisionRecord
    review_record: ReviewRecord | None


class ReviewQueueMetrics(BaseModel):
    active_review_count: int
    pending_count: int
    assigned_count: int
    in_review_count: int
    reopened_count: int
    breached_sla_count: int
    active_by_risk_band: dict[RiskBand, int]
    breached_sla_by_risk_band: dict[RiskBand, int]
    average_queue_age_hours: float
    oldest_queue_age_hours: float
    sla_target_hours: float


class ComplianceSummaryReport(BaseModel):
    generated_at: str
    total_decisions: int
    policy_violation_confirmed_count: int
    cleared_count: int
    insufficient_evidence_count: int
    investigation_required_count: int
    active_investigation_count: int
    completed_investigation_count: int
    override_count: int
    reopened_case_count: int
    decision_count_by_risk_band: dict[RiskBand, int]
    active_investigation_count_by_risk_band: dict[RiskBand, int]
    reopen_reason_counts: dict[ReopenReason, int]
