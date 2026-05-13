from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from jwt import InvalidTokenError

from app.engine import calculate_review_queue_metrics, evaluate_incident_case, load_rule, load_rules
from app.models import (
    ComplianceSummaryReport,
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
    IncidentCase,
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
    title="Employee Conduct Compliance Agentic AI",
    version="0.2.0",
    description=(
        "A compliance evaluation system for employee conduct incidents including harassment, discrimination, client treatment, and international employment governance."
    ),
)

init_db()


AUTH_ALGORITHM = "HS256"
AUTH_SECRET_ENV_VAR = "COMPLIANCE_AUTH_SECRET"
AUTH_KEYS_JSON_ENV_VAR = "COMPLIANCE_AUTH_KEYS_JSON"
AUTH_ISSUER_ENV_VAR = "COMPLIANCE_AUTH_ISSUER"
AUTH_AUDIENCE_ENV_VAR = "COMPLIANCE_AUTH_AUDIENCE"
ALLOW_INSECURE_HEADERS_ENV_VAR = "COMPLIANCE_ALLOW_INSECURE_HEADERS"


def _get_auth_secret() -> str:
    secret = os.getenv(AUTH_SECRET_ENV_VAR)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing {AUTH_SECRET_ENV_VAR} environment configuration",
        )

    return secret


def _allow_insecure_headers() -> bool:
    value = os.getenv(ALLOW_INSECURE_HEADERS_ENV_VAR, "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _get_auth_keys() -> dict[str, str]:
    raw_keys = os.getenv(AUTH_KEYS_JSON_ENV_VAR)
    if not raw_keys:
        return {}

    try:
        parsed_keys = json.loads(raw_keys)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid JSON in {AUTH_KEYS_JSON_ENV_VAR}",
        ) from error

    if not isinstance(parsed_keys, dict) or not parsed_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{AUTH_KEYS_JSON_ENV_VAR} must be a non-empty object",
        )

    normalized_keys: dict[str, str] = {}
    for key_id, key_secret in parsed_keys.items():
        if not isinstance(key_id, str) or not key_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{AUTH_KEYS_JSON_ENV_VAR} contains invalid key identifier",
            )
        if not isinstance(key_secret, str) or not key_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{AUTH_KEYS_JSON_ENV_VAR} contains invalid secret value",
            )
        normalized_keys[key_id] = key_secret

    return normalized_keys


def _select_auth_secret(token: str) -> str:
    auth_keys = _get_auth_keys()
    if auth_keys:
        try:
            unverified_header = jwt.get_unverified_header(token)
        except InvalidTokenError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from error

        key_id = unverified_header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token missing key identifier",
            )

        secret = auth_keys.get(key_id)
        if secret is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token key identifier is not trusted",
            )

        return secret

    return _get_auth_secret()


def _decode_token_claims(token: str) -> dict:
    secret = _select_auth_secret(token)
    issuer = os.getenv(AUTH_ISSUER_ENV_VAR)
    audience = os.getenv(AUTH_AUDIENCE_ENV_VAR)

    decode_options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_sub": True,
        "verify_iss": bool(issuer),
        "verify_aud": bool(audience),
    }

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[AUTH_ALGORITHM],
            issuer=issuer,
            audience=audience,
            options=decode_options,
        )
    except InvalidTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from error


def _parse_bearer_token(authorization: str) -> str:
    auth_scheme, _, token = authorization.partition(" ")

    if auth_scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer token format",
        )

    return token


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: UserRole


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> AuthContext:
    if authorization is not None:
        token = _parse_bearer_token(authorization)
        claims = _decode_token_claims(token)

        user_id = claims.get("sub")
        role_claim = claims.get("role")

        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing valid subject claim")

        if not isinstance(role_claim, str) or not role_claim:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing valid role claim")

        try:
            role = UserRole(role_claim)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user role") from error

        return AuthContext(user_id=user_id, role=role)

    if not _allow_insecure_headers():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
        )

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
    incident_case: IncidentCase,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.EMPLOYEE, UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
) -> DecisionRecord:
    try:
        decision_record = evaluate_incident_case(incident_case)
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
        policy_violation_confirmed_count=sum(1 for decision in decisions if decision.decision == DecisionState.POLICY_VIOLATION_CONFIRMED),
        cleared_count=sum(1 for decision in decisions if decision.decision == DecisionState.CLEARED),
        insufficient_evidence_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.INSUFFICIENT_EVIDENCE
        ),
        investigation_required_count=sum(
            1 for decision in decisions if decision.decision == DecisionState.INVESTIGATION_REQUIRED
        ),
        active_review_count=sum(1 for decision in decisions if decision.review_required),
        completed_review_count=sum(1 for decision in decisions if decision.review_status == ReviewStatus.COMPLETED),
        override_count=sum(1 for decision in decisions if decision.final_reviewer_outcome == ReviewerOutcome.OVERRIDDEN),
        reopened_case_count=sum(1 for decision in decisions if decision.review_cycle_id > 1),
        decision_count_by_risk_band=decision_count_by_risk_band,
        active_review_count_by_risk_band=active_review_count_by_risk_band,
        reopen_reason_counts=reopen_reason_counts,
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
