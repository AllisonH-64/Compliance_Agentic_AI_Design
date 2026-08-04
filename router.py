"""
Add this router to your existing app/main.py:

    from agent_module.router import agent_router
    app.include_router(agent_router)

This adds a single new endpoint that lets an analyst submit a raw,
unstructured incident report and get back the agent's structured
triage — without touching any of your existing deterministic routes.
"""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from orchestrator import run_agent

agent_router = APIRouter(prefix="/agent", tags=["agent"])


class IncidentReportRequest(BaseModel):
    report_text: str


@agent_router.post("/triage")
def triage_incident(
    req: IncidentReportRequest,
    # Reuse whatever auth dependency app/main.py already uses here,
    # e.g. Depends(get_current_user), so this inherits your existing
    # role-based access control instead of adding a separate scheme.
    x_user_id: str = Header(default="unknown"),
):
    result = run_agent(req.report_text, submitted_by=x_user_id)
    return result


# ---------------------------------------------------------------------------
# Standalone usage example (run directly: python router.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_report = """
    An employee reported that a manager made repeated comments about
    a coworker's national origin during team meetings over the past
    two months, and the coworker has filed one prior informal complaint
    about the same manager. This occurred at the Berlin office.
    """
    result = run_agent(sample_report, submitted_by="analyst_jsmith")
    print(result["response"])
    print("Severity band:", result["severity_band"])
    if result["pending_human_confirmation"]:
        print("PENDING HUMAN CONFIRMATION:", result["pending_human_confirmation"])
