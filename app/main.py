from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from app.auth import AuthContext, get_current_user, require_roles
from app.engine import calculate_dashboard_summary, calculate_review_queue_metrics, evaluate_vendor_case, load_rule, load_rules
from app.models import (
    ComplianceSummaryReport,
    DashboardSummary,
    DEFAULT_CONTROL_ID,
    DecisionRecord,
    DecisionState,
    ReopenReason,
    ReviewAssignment,
    ReviewQueueMetrics,
    ReviewQueueItem,
    ReviewReopen,
    ReviewRecord,
    ReviewerOutcome,
    RiskBand,
    ReviewStart,
    ReviewStatus,
    RuleMetadata,
    ReviewSubmission,
    VendorTransaction,
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
    title="Vendor Due-Diligence Gate",
    version="0.3.0",
    description=(
        "A compliance evaluation system that gates vendor spend on approval thresholds and vendor "
        "due-diligence screening before a transaction is allowed to proceed."
    ),
)

init_db()


try:
    # Optional: the LLM triage agent (orchestrator.py/router.py/tools.py at the repo
    # root) is not part of the deployed Lambda package (see infra/app.py) and needs
    # the `anthropic` package plus an ANTHROPIC_API_KEY, neither of which the core
    # app depends on. Mounting it is best-effort so the core app works either way.
    from router import agent_router

    app.include_router(agent_router)
except ImportError:
    pass


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
    vendor_transaction: VendorTransaction,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.EMPLOYEE, UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
) -> DecisionRecord:
    try:
        decision_record = evaluate_vendor_case(vendor_transaction)
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
    decision_count_by_risk_band = {band: 0 for band in RiskBand}
    active_review_count_by_risk_band = {band: 0 for band in RiskBand}
    reopen_reason_counts = {reason: 0 for reason in ReopenReason}

    for decision in decisions:
        decision_count_by_risk_band[decision.risk_band] += 1

        if decision.review_required:
            active_review_count_by_risk_band[decision.risk_band] += 1

        if decision.reopen_reason is not None:
            reopen_reason_counts[decision.reopen_reason] += 1

    return ComplianceSummaryReport(
        generated_at=datetime.now(UTC).isoformat(),
        total_decisions=len(decisions),
        approved_count=sum(1 for decision in decisions if decision.decision == DecisionState.APPROVED),
        blocked_count=sum(1 for decision in decisions if decision.decision == DecisionState.BLOCKED),
        insufficient_evidence_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.INSUFFICIENT_EVIDENCE
        ),
        human_review_required_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.HUMAN_REVIEW_REQUIRED
        ),
        active_review_count=sum(1 for decision in decisions if decision.review_required),
        completed_review_count=sum(1 for decision in decisions if decision.review_status == ReviewStatus.COMPLETED),
        override_count=sum(1 for decision in decisions if decision.final_reviewer_outcome == ReviewerOutcome.OVERRIDDEN),
        reopened_case_count=sum(1 for decision in decisions if decision.review_cycle_id > 1),
        decision_count_by_risk_band=decision_count_by_risk_band,
        active_review_count_by_risk_band=active_review_count_by_risk_band,
        reopen_reason_counts=reopen_reason_counts,
    )


@app.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    _: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER, UserRole.AUDITOR)),
    ],
) -> DashboardSummary:
    return calculate_dashboard_summary(list_decisions())


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


@app.post("/reviews/{case_id}/reopen", response_model=DecisionRecord)
def reopen_review(
    case_id: str,
    reopen_request: ReviewReopen,
    current_user: Annotated[AuthContext, Depends(require_roles(UserRole.COMPLIANCE_MANAGER))],
) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    if decision_record.review_status != ReviewStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Only completed reviews can be reopened")

    reopened_decision = decision_record.model_copy(
        update={
            "decision": DecisionState.HUMAN_REVIEW_REQUIRED,
            "reasoning_summary": f"Case reopened for additional review: {reopen_request.notes}",
            "recommended_action": "Review reopened. Reassign and complete a new adjudication cycle.",
            "review_required": True,
            "review_status": ReviewStatus.REOPENED,
            "review_cycle_id": decision_record.review_cycle_id + 1,
            "reopen_reason": reopen_request.reason,
            "assigned_reviewer_id": None,
            "assigned_at": None,
            "review_started_at": None,
            "final_reviewer_outcome": None,
            "final_reviewed_at": None,
        }
    )

    save_decision(
        reopened_decision,
        event_type="case_reopened",
        actor_id=current_user.user_id,
        actor_role=current_user.role.value,
    )
    return reopened_decision
