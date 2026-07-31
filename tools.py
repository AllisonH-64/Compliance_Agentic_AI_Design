"""
Tool wrappers around the existing FastAPI Compliance service.

These do NOT reimplement any compliance logic. Every function here is a thin
HTTP call into your existing app/main.py routes. The deterministic severity
scoring, escalation thresholds, and rule catalogs stay exactly where they are
today (app/ + data/rules/) — the agent only ever reads results from them.

Adjust BASE_URL, auth handling, and payload shapes to match your actual
app/main.py route signatures once you compare against this file.
"""

import os
import httpx

BASE_URL = os.environ.get("COMPLIANCE_API_BASE_URL", "http://127.0.0.1:8000")

# Service-level token for the agent's own calls into the API.
# Should be scoped to the least-privilege role the agent needs
# (recommend a dedicated "compliance_agent" role, not compliance_manager).
AGENT_SERVICE_TOKEN = os.environ.get("COMPLIANCE_AGENT_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {AGENT_SERVICE_TOKEN}"}


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, headers=_headers(), timeout=15.0)


# ---------------------------------------------------------------------------
# Tool implementations — each maps 1:1 to an existing endpoint
# ---------------------------------------------------------------------------

def get_active_rules() -> dict:
    """GET /rules/current — fetch the current versioned rule catalog."""
    with _client() as c:
        r = c.get("/rules/current")
        r.raise_for_status()
        return r.json()


def evaluate_incident(payload: dict) -> dict:
    """
    POST /evaluate — run the deterministic severity/escalation engine
    on a structured incident report. This is the ONLY source of truth
    for severity band. The agent must never compute or override this itself.

    Expected payload shape (adjust to match app/main.py's request model):
    {
        "control_id": "CONDUCT-HARASSMENT-001",
        "description": "...",
        "protected_characteristics": [...],
        "prior_complaints": 0,
        "involved_parties": [...],
        "jurisdiction": "US-CA"
    }
    """
    with _client() as c:
        r = c.post("/evaluate", json=payload)
        r.raise_for_status()
        return r.json()


def get_open_investigations() -> dict:
    """GET /investigations/queue — active cases requiring action."""
    with _client() as c:
        r = c.get("/investigations/queue")
        r.raise_for_status()
        return r.json()


def get_decision(case_id: str) -> dict:
    """GET /decisions/{case_id} — retrieve a prior compliance decision."""
    with _client() as c:
        r = c.get(f"/decisions/{case_id}")
        r.raise_for_status()
        return r.json()


def assign_investigator(case_id: str, investigator: str) -> dict:
    """
    POST /reviews/{case_id}/assign — assign an investigator.

    NOTE: For HIGH/CRITICAL severity, this should require human
    confirmation before being called — see orchestrator.py's
    requires_human_confirmation() gate. Do not let the agent call
    this autonomously for high-severity cases.
    """
    with _client() as c:
        r = c.post(f"/reviews/{case_id}/assign", json={"investigator": investigator})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Anthropic tool-use schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_active_rules",
        "description": (
            "Fetch the current versioned catalog of conduct compliance rules "
            "(CONDUCT-HARASSMENT-001, CONDUCT-DISCRIMINATION-001, "
            "CONDUCT-CLIENT-001, CONDUCT-INTL-GOV-001). Call this first to "
            "ground your reasoning in the current rule definitions rather "
            "than assuming them."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "evaluate_incident",
        "description": (
            "Submit a structured incident report to the deterministic "
            "compliance evaluation engine. Returns the authoritative "
            "severity band (LOW/MEDIUM/HIGH/CRITICAL) and escalation "
            "requirement. This is the ONLY source of truth for severity — "
            "never state a severity band that didn't come from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "enum": [
                        "CONDUCT-HARASSMENT-001",
                        "CONDUCT-DISCRIMINATION-001",
                        "CONDUCT-CLIENT-001",
                        "CONDUCT-INTL-GOV-001",
                    ],
                },
                "description": {"type": "string"},
                "protected_characteristics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "prior_complaints": {"type": "integer"},
                "involved_parties": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "jurisdiction": {"type": "string"},
            },
            "required": ["control_id", "description"],
        },
    },
    {
        "name": "get_open_investigations",
        "description": "List active investigation cases currently in the queue.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "assign_investigator",
        "description": (
            "Assign an investigator to a case. For HIGH/CRITICAL severity "
            "cases, this call will be blocked unless a human has already "
            "confirmed the assignment — propose the assignment in your "
            "response instead of calling this tool directly for those cases."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "investigator": {"type": "string"},
            },
            "required": ["case_id", "investigator"],
        },
    },
]

TOOL_IMPLEMENTATIONS = {
    "get_active_rules": lambda **kw: get_active_rules(),
    "evaluate_incident": lambda **kw: evaluate_incident(kw.get("payload", kw)),
    "get_open_investigations": lambda **kw: get_open_investigations(),
    "assign_investigator": lambda **kw: assign_investigator(
        kw["case_id"], kw["investigator"]
    ),
}
