from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from app.engine import evaluate_transaction_case, load_rule
from app.models import (
    DecisionRecord,
    DecisionState,
    ReviewAssignment,
    ReviewQueueItem,
    ReviewRecord,
    ReviewStart,
    ReviewStatus,
    ReviewSubmission,
    TransactionCase,
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
        "A thin vertical slice for approval-threshold compliance checks with deterministic policy evaluation."
    ),
)

init_db()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rules/current")
def current_rule() -> dict[str, str | float]:
    return load_rule().model_dump()


@app.post("/evaluate", response_model=DecisionRecord)
def evaluate_case(transaction_case: TransactionCase) -> DecisionRecord:
    decision_record = evaluate_transaction_case(transaction_case)
    save_decision(decision_record)
    return decision_record


@app.get("/decisions", response_model=list[DecisionRecord])
def get_decisions() -> list[DecisionRecord]:
    return list_decisions()


@app.get("/decisions/{case_id}", response_model=DecisionRecord)
def get_decision_by_case_id(case_id: str) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    return decision_record


@app.get("/reviews/queue", response_model=list[ReviewQueueItem])
def get_review_queue() -> list[ReviewQueueItem]:
    return list_review_queue()


@app.get("/reviews/{case_id}", response_model=ReviewRecord)
def get_review_by_case_id(case_id: str) -> ReviewRecord:
    review_record = get_review(case_id)

    if review_record is None:
        raise HTTPException(status_code=404, detail="Review record not found")

    return review_record


@app.post("/reviews/{case_id}/assign", response_model=DecisionRecord)
def assign_review(case_id: str, review_assignment: ReviewAssignment) -> DecisionRecord:
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
    save_decision(assigned_decision)
    return assigned_decision


@app.post("/reviews/{case_id}/start", response_model=DecisionRecord)
def start_review(case_id: str, review_start: ReviewStart) -> DecisionRecord:
    decision_record = get_decision(case_id)

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Decision record not found")

    if not decision_record.review_required:
        raise HTTPException(status_code=400, detail="Decision does not require human review")

    assigned_reviewer_id = decision_record.assigned_reviewer_id
    if assigned_reviewer_id is not None and assigned_reviewer_id != review_start.reviewer_id:
        raise HTTPException(status_code=400, detail="Review is assigned to a different reviewer")

    in_review_decision = decision_record.model_copy(
        update={
            "review_status": ReviewStatus.IN_REVIEW,
            "assigned_reviewer_id": review_start.reviewer_id,
            "assigned_at": decision_record.assigned_at or datetime.now(UTC).isoformat(),
            "review_started_at": datetime.now(UTC).isoformat(),
        }
    )
    save_decision(in_review_decision)
    return in_review_decision


@app.post("/reviews/{case_id}", response_model=ReviewRecord)
def submit_review(case_id: str, review_submission: ReviewSubmission) -> ReviewRecord:
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

    save_review(review_record)
    save_decision(finalized_decision)
    return review_record
