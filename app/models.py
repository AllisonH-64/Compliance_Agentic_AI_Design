from enum import Enum

from pydantic import BaseModel, Field


DEFAULT_CONTROL_ID = "ETH-GIFT-001"


class DecisionState(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


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


class RecipientType(str, Enum):
    EMPLOYEE = "employee"
    CUSTOMER = "customer"
    VENDOR = "vendor"
    GOVERNMENT_OFFICIAL = "government_official"
    STATE_OWNED_ENTITY = "state_owned_entity"
    UNKNOWN = "unknown"


class MarketRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventContext(str, Enum):
    CONTRACT_NEGOTIATION = "contract_negotiation"
    ACTIVE_TENDER = "active_tender"
    POST_AWARD = "post_award"
    RELATIONSHIP_MANAGEMENT = "relationship_management"
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


class ApprovalRecord(BaseModel):
    approver_role: str = Field(..., description="Role that approved the case")
    approved: bool = Field(..., description="Whether an approval was granted")


class ReceiptRecord(BaseModel):
    attached: bool = Field(..., description="Whether a receipt or invoice image was attached")
    document_id: str | None = Field(default=None, description="Identifier for the attached receipt evidence")


class TransactionCase(BaseModel):
    case_id: str = Field(..., description="Unique identifier for the compliance case")
    transaction_id: str = Field(..., description="Unique identifier for the spend submission or transaction")
    control_id: str = Field(
        default=DEFAULT_CONTROL_ID,
        description="Identifier for the rule control to evaluate against",
    )
    amount: float = Field(..., gt=0, description="Submitted spend amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO currency code")
    requestor_role: str = Field(..., description="Role of the user submitting the case")
    approval_record: ApprovalRecord | None = Field(
        default=None,
        description="Approval evidence attached to the case",
    )
    receipt_record: ReceiptRecord | None = Field(
        default=None,
        description="Receipt evidence attached to the case when required by the selected control",
    )
    recipient_type: RecipientType | None = Field(
        default=None,
        description="Recipient classification for contextual risk scoring",
    )
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO country code where the interaction occurred",
    )
    market_risk_level: MarketRiskLevel | None = Field(
        default=None,
        description="Compliance-managed geography risk tier",
    )
    business_purpose: str | None = Field(
        default=None,
        description="Business purpose or justification for the interaction",
    )
    prior_interactions_12m: int = Field(
        default=0,
        ge=0,
        description="Count of prior interactions with the same recipient in the last 12 months",
    )
    exception_reference: str | None = Field(
        default=None,
        description="Optional approved exception or waiver identifier",
    )
    event_context: EventContext | None = Field(
        default=None,
        description="Business context in which the spend occurred",
    )
    submitted_by_role: str | None = Field(
        default=None,
        description="Submitting employee role used for segregation-of-duties checks",
    )
    beneficiary_identifier: str | None = Field(
        default=None,
        description="Recipient or organization identifier used for pattern detection",
    )


class RuleMetadata(BaseModel):
    control_id: str
    control_domain: str
    policy_name: str
    policy_version: str
    description: str
    threshold_amount: float
    required_evidence: list[str]
    required_approver_role: str | None = None
    required_currency: str | None = None


class DecisionRecord(BaseModel):
    case_id: str
    transaction_id: str
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
    escalation_decision: str = "auto_close"
    escalation_policy_version: str = "risk-signals-v1"
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
    compliant_count: int
    non_compliant_count: int
    insufficient_evidence_count: int
    human_review_required_count: int
    active_review_count: int
    completed_review_count: int
    override_count: int
    reopened_case_count: int
    decision_count_by_risk_band: dict[RiskBand, int]
    active_review_count_by_risk_band: dict[RiskBand, int]
    reopen_reason_counts: dict[ReopenReason, int]
