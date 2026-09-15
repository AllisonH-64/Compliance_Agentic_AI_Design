from enum import Enum

from pydantic import BaseModel, Field


DEFAULT_CONTROL_ID = "PROC-SPEND-APPROVAL-001"


class DecisionState(str, Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"
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


class MarketRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
    approver_role: str = Field(..., description="Role of the person who approved or denied the spend")
    approved: bool = Field(..., description="Whether the approver signed off on the transaction")
    document_id: str | None = Field(default=None, description="Identifier for the approval record document")


class ConflictOfInterestRecord(BaseModel):
    disclosed: bool = Field(..., description="Whether the potential conflict of interest has been formally disclosed")
    cleared: bool | None = Field(
        default=None,
        description="Compliance decision on the disclosed conflict: True cleared, False rejected, None still pending",
    )
    document_id: str | None = Field(default=None, description="Identifier for the conflict-of-interest disclosure document")


class ReceiptRecord(BaseModel):
    attached: bool = Field(..., description="Whether a receipt or itemized invoice has been attached for this expense")
    receipt_total: float | None = Field(
        default=None,
        description="Total amount shown on the attached receipt, for reconciliation against the claimed amount",
    )
    document_id: str | None = Field(default=None, description="Identifier for the receipt document")


class VendorScreeningRecord(BaseModel):
    completed: bool = Field(..., description="Whether vendor due-diligence screening has been completed")
    sanctions_check_passed: bool | None = Field(
        default=None,
        description="Result of sanctions/watchlist screening, if completed",
    )
    enhanced_due_diligence_completed: bool = Field(
        default=False,
        description="Whether enhanced due diligence (e.g. local counsel review) has been completed, required for high-risk jurisdictions",
    )
    document_id: str | None = Field(default=None, description="Identifier for the screening record document")


class VendorTransaction(BaseModel):
    case_id: str = Field(..., description="Unique identifier for the compliance case")
    transaction_id: str = Field(..., description="Unique identifier for the purchase order or transaction")
    control_id: str = Field(
        default=DEFAULT_CONTROL_ID,
        description="Identifier for the rule control to evaluate against",
    )
    vendor_name: str = Field(..., description="Name of the vendor receiving the spend")
    vendor_id: str | None = Field(default=None, description="Identifier for the vendor in the vendor master")
    new_vendor: bool = Field(
        default=False,
        description="Whether this is the vendor's first transaction with the organization",
    )
    vendor_risk_level: MarketRiskLevel | None = Field(
        default=None,
        description="Compliance-managed risk tier for the vendor",
    )
    requestor_role: str = Field(..., description="Role of the person requesting the spend")
    amount: float = Field(..., ge=0, description="Transaction amount")
    currency: str = Field(..., description="ISO currency code for the transaction amount")
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO country code where the vendor is based",
    )
    business_justification: str = Field(..., description="Business justification for the transaction")
    approval_record: ApprovalRecord | None = Field(
        default=None,
        description="Primary approval evidence attached to the transaction",
    )
    second_approval_record: ApprovalRecord | None = Field(
        default=None,
        description="Secondary approval evidence required above the dual-approval threshold",
    )
    vendor_screening_record: VendorScreeningRecord | None = Field(
        default=None,
        description="Vendor due-diligence screening evidence attached when required by the selected control",
    )
    potential_conflict_of_interest: bool = Field(
        default=False,
        description="Whether a potential conflict of interest with the vendor has been flagged (e.g. personal, familial, or financial relationship)",
    )
    conflict_of_interest_record: ConflictOfInterestRecord | None = Field(
        default=None,
        description="Conflict-of-interest disclosure and compliance clearance evidence",
    )
    receipt_record: ReceiptRecord | None = Field(
        default=None,
        description="Receipt or itemized invoice evidence attached to the expense",
    )
    prior_flagged_transactions_12m: int = Field(
        default=0,
        ge=0,
        description="Count of prior flagged transactions involving the same vendor in the last 12 months",
    )


class RuleMetadata(BaseModel):
    control_id: str
    control_domain: str
    policy_name: str
    policy_version: str
    description: str
    severity_threshold: float | None = Field(default=None, description="Minimum severity score to trigger action")
    required_evidence: list[str]
    required_reviewer_role: str | None = None
    international_applicability: list[str] = Field(default_factory=lambda: ["ALL"])
    escalation_triggers: dict | None = Field(default=None, description="Conditions that trigger escalation")


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
    escalation_policy_version: str = "vendor-due-diligence-v1"
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
    approved_count: int
    blocked_count: int
    insufficient_evidence_count: int
    human_review_required_count: int
    active_review_count: int
    completed_review_count: int
    override_count: int
    reopened_case_count: int
    decision_count_by_risk_band: dict[RiskBand, int]
    active_review_count_by_risk_band: dict[RiskBand, int]
    reopen_reason_counts: dict[ReopenReason, int]
