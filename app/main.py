from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.engine import calculate_review_queue_metrics, evaluate_transaction_case, load_rule, load_rules
from app.models import (
    ComplianceSummaryReport,
    DEFAULT_CONTROL_ID,
    DecisionRecord,
    DecisionState,
    ReviewAssignment,
    ReviewQueueMetrics,
    ReviewQueueItem,
    ReviewRecord,
    ReviewStart,
    ReviewStatus,
    RuleMetadata,
    ReviewSubmission,
    TransactionCase,
    UserRole,
)
from app.storage import (
    get_decision,
    get_review,
    init_db,
    list_decisions,
    list_review_queue,
    save_decision,
    save_review,
)


app = FastAPI(
    title="Compliance Agentic AI MVP",
    version="0.1.0",
    description=(
        "A thin vertical slice for gifts-and-hospitality compliance checks with deterministic policy evaluation."
    ),
)

init_db()


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: UserRole


def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> AuthContext:
    if x_user_id is None or x_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id or X-User-Role header",
        )

    try:
        role = UserRole(x_user_role)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user role") from error

    return AuthContext(user_id=x_user_id, role=role)


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: Annotated[AuthContext, Depends(get_current_user)]) -> AuthContext:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User role not permitted")

        return current_user

    return dependency


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rules", response_model=list[RuleMetadata])
def get_rules() -> list[RuleMetadata]:
    return load_rules()


@app.get("/rules/current", response_model=RuleMetadata)
def current_rule(control_id: str | None = None) -> RuleMetadata:
    try:
        return load_rule(control_id or DEFAULT_CONTROL_ID)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/rules/{control_id}", response_model=RuleMetadata)
def get_rule(control_id: str) -> RuleMetadata:
    try:
        return load_rule(control_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/evaluate", response_model=DecisionRecord)
def evaluate_case(
    transaction_case: TransactionCase,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.EMPLOYEE, UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
) -> DecisionRecord:
    try:
        decision_record = evaluate_transaction_case(transaction_case)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    save_decision(
        decision_record,
        event_type="decision_evaluated",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    return decision_record


@app.get("/decisions", response_model=list[DecisionRecord])
def get_decisions(
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> list[DecisionRecord]:
    return list_decisions()


@app.get("/decisions/{case_id}", response_model=DecisionRecord)
def get_decision_by_case_id(
    case_id: str,
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    return decision_record


@app.get("/reviews/queue", response_model=list[ReviewQueueItem])
def get_review_queue(
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> list[ReviewQueueItem]:
    return list_review_queue()


@app.get("/reviews/metrics", response_model=ReviewQueueMetrics)
def get_review_metrics(
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> ReviewQueueMetrics:
    return calculate_review_queue_metrics(list_decisions())


@app.get("/reports/summary", response_model=ComplianceSummaryReport)
def get_summary_report(
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> ComplianceSummaryReport:
    decisions = list_decisions()

    return ComplianceSummaryReport(
        generated_at=datetime.now(UTC).isoformat(),
        total_decisions=len(decisions),
        compliant_count=sum(1 for decision in decisions if decision.decision == DecisionState.COMPLIANT),
        non_compliant_count=sum(1 for decision in decisions if decision.decision == DecisionState.NON_COMPLIANT),
        insufficient_evidence_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.INSUFFICIENT_EVIDENCE
        ),
        human_review_required_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.HUMAN_REVIEW_REQUIRED
        ),
        active_review_count=sum(1 for decision in decisions if decision.review_required),
        completed_review_count=sum(1 for decision in decisions if decision.review_status == ReviewStatus.COMPLETED),
        override_count=sum(1 for decision in decisions if decision.final_reviewer_outcome == "overridden"),
    )


@app.get("/reviews/{case_id}", response_model=ReviewRecord)
def get_review_by_case_id(
    case_id: str,
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> ReviewRecord:
    review_record = get_review(case_id)

    if review_record is None:
        raise HTTPException(status_code=404, detail="Review record not found")

    return review_record


@app.post("/reviews/{case_id}/assign", response_model=DecisionRecord)
def assign_review(
    case_id: str,
    review_assignment: ReviewAssignment,
    current_user: Annotated[AuthContext, Depends(require_roles(UserRole.COMPLIANCE_MANAGER))],
) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    if not decision_record.review_required:
        raise HTTPException(status_code=400, detail="Decision does not require human review")

    if decision_record.review_status == ReviewStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Review has already been completed")

    assigned_decision = decision_record.model_copy(
        update={
            "review_status": ReviewStatus.ASSIGNED,
            "assigned_reviewer_id": review_assignment.reviewer_id,
            "assigned_at": datetime.now(UTC).isoformat(),
        }
    )
    save_decision(
        assigned_decision,
        event_type="review_assigned",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    return assigned_decision


@app.post("/reviews/{case_id}/start", response_model=DecisionRecord)
def start_review(
    case_id: str,
    review_start: ReviewStart,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    if not decision_record.review_required:
        raise HTTPException(status_code=400, detail="Decision does not require human review")

    assigned_reviewer_id = decision_record.assigned_reviewer_id
    if assigned_reviewer_id is not None and assigned_reviewer_id != review_start.reviewer_id:
        raise HTTPException(status_code=400, detail="Review is assigned to a different reviewer")

    if current_user.user_id != review_start.reviewer_id:
        raise HTTPException(status_code=403, detail="Authenticated user must match reviewer_id")

    in_review_decision = decision_record.model_copy(
        update={
            "review_status": ReviewStatus.IN_REVIEW,
            "assigned_reviewer_id": review_start.reviewer_id,
            "assigned_at": decision_record.assigned_at or datetime.now(UTC).isoformat(),
            "review_started_at": datetime.now(UTC).isoformat(),
        }
    )
    save_decision(
        in_review_decision,
        event_type="review_started",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    return in_review_decision


@app.post("/reviews/{case_id}", response_model=ReviewRecord)
def submit_review(
    case_id: str,
    review_submission: ReviewSubmission,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
) -> ReviewRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    if not decision_record.review_required:
        raise HTTPException(status_code=400, detail="Decision does not require human review")

    if review_submission.final_decision == DecisionState.HUMAN_REVIEW_REQUIRED:
        raise HTTPException(status_code=400, detail="Final decision cannot remain human_review_required")

    assigned_reviewer_id = decision_record.assigned_reviewer_id
    if assigned_reviewer_id is not None and assigned_reviewer_id != review_submission.reviewer_id:
        raise HTTPException(status_code=400, detail="Review is assigned to a different reviewer")

    if current_user.user_id != review_submission.reviewer_id:
        raise HTTPException(status_code=403, detail="Authenticated user must match reviewer_id")

    review_record = ReviewRecord(
        case_id=case_id,
        reviewer_id=review_submission.reviewer_id,
        outcome=review_submission.outcome,
        final_decision=review_submission.final_decision,
        notes=review_submission.notes,
        reviewed_at=datetime.now(UTC).isoformat(),
    )

    finalized_decision = decision_record.model_copy(
        update={
            "decision": review_submission.final_decision,
            "review_required": False,
            "review_status": ReviewStatus.COMPLETED,
            "assigned_reviewer_id": decision_record.assigned_reviewer_id or review_submission.reviewer_id,
            "assigned_at": decision_record.assigned_at,
            "review_started_at": decision_record.review_started_at or datetime.now(UTC).isoformat(),
            "final_reviewer_outcome": review_submission.outcome,
            "final_reviewed_at": review_record.reviewed_at,
            "recommended_action": "Review completed. Follow the documented reviewer disposition.",
        }
    )

    save_review(
        review_record,
        event_type="review_submitted",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    save_decision(
        finalized_decision,
        event_type="review_completed",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    return review_record
