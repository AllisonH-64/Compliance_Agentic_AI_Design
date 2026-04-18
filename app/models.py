from enum import Enum

from pydantic import BaseModel, Field


DEFAULT_CONTROL_ID = "FIN-APPROVAL-001"


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
    COMPLETED = "completed"


class ApprovalRecord(BaseModel):
    approver_role: str = Field(..., description="Role that approved the transaction")
    approved: bool = Field(..., description="Whether an approval was granted")


class ReceiptRecord(BaseModel):
    attached: bool = Field(..., description="Whether a receipt or invoice image was attached")
    document_id: str | None = Field(default=None, description="Identifier for the attached receipt evidence")


class TransactionCase(BaseModel):
    case_id: str = Field(..., description="Unique identifier for the compliance case")
    transaction_id: str = Field(..., description="Unique identifier for the transaction")
    control_id: str = Field(
        default=DEFAULT_CONTROL_ID,
        description="Identifier for the rule control to evaluate against",
    )
    amount: float = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO currency code")
    requestor_role: str = Field(..., description="Role of the user requesting the transaction")
    approval_record: ApprovalRecord | None = Field(
        default=None,
        description="Approval evidence attached to the case",
    )
    receipt_record: ReceiptRecord | None = Field(
        default=None,
        description="Receipt evidence attached to the case when required by the selected control",
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
    breached_sla_count: int
    average_queue_age_hours: float
    oldest_queue_age_hours: float
    sla_target_hours: float
