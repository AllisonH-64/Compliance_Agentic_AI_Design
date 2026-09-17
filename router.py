"""
Adds a single endpoint that lets an analyst submit a raw, unstructured transaction
description and get back the agent's structured triage -- without touching any of
the existing deterministic routes in app/main.py.

Mounted automatically by app/main.py (best-effort -- see the try/except there) when
this module and its dependencies (orchestrator.py, tools.py, the `anthropic`
package) are importable. Not part of the AWS Lambda deployment package (see
infra/app.py) -- it's local/optional, not core to the deployed service.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import AuthContext, require_roles
from app.models import UserRole
from orchestrator import run_agent

agent_router = APIRouter(prefix="/agent", tags=["agent"])


class TransactionDescriptionRequest(BaseModel):
    description: str


@agent_router.post("/triage")
def triage_transaction(
    request: TransactionDescriptionRequest,
    current_user: Annotated[
        AuthContext,
        Depends(require_roles(UserRole.EMPLOYEE, UserRole.COMPLIANCE_ANALYST, UserRole.COMPLIANCE_MANAGER)),
    ],
):
    # This endpoint is explicitly optional (see README/AGENTS.md), so a
    # misconfiguration (no ANTHROPIC_API_KEY, an invalid key, the model call
    # failing) should read as "this feature isn't set up" rather than look like
    # the core app crashed -- surface it as a clear 503, not an opaque 500.
    try:
        return run_agent(request.description, submitted_by=current_user.user_id)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM triage agent is unavailable -- confirm ANTHROPIC_API_KEY is set and valid. "
                f"Underlying error: {error}"
            ),
        ) from error


# ---------------------------------------------------------------------------
# Standalone usage example (run directly: python router.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_transaction = """
    A sales manager is requesting a $2,500 payment to Meridian Consulting Group
    for a market research engagement ahead of the Q4 launch. This is a routine
    vendor for spend-approval evaluation.
    """
    result = run_agent(sample_transaction, submitted_by="analyst_jsmith")
    print(result["response"])
    print("Risk band:", result["risk_band"])
    if result["pending_human_confirmation"]:
        print("PENDING HUMAN CONFIRMATION:", result["pending_human_confirmation"])
