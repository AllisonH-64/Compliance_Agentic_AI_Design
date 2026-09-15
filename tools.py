"""
Tool wrappers around the existing FastAPI Vendor Due-Diligence Gate service.

These do NOT reimplement any compliance logic. Every function here is a thin
HTTP call into the existing app/main.py routes. The deterministic risk scoring,
escalation thresholds, and rule catalogs stay exactly where they are today
(app/ + data/rules/) -- the agent only ever reads results from them.

Calls back into the running app over HTTP (COMPLIANCE_API_BASE_URL) rather than
calling app.engine directly, so the agent goes through the same auth/RBAC path as
every other caller -- it has no special access.
"""

import os
import httpx

BASE_URL = os.environ.get("COMPLIANCE_API_BASE_URL", "http://127.0.0.1:8000")

# The agent's own identity for its calls back into the API. If COMPLIANCE_AGENT_TOKEN
# is set, it's sent as a signed bearer token (production / anywhere COMPLIANCE_AUTH_SECRET
# or Cognito is enforced); otherwise it falls back to the insecure X-User-Id/X-User-Role
# headers, which only work when the API has COMPLIANCE_ALLOW_INSECURE_HEADERS=true (e.g.
# dev_server.py) -- convenient for local use, refused by the API otherwise.
AGENT_SERVICE_TOKEN = os.environ.get("COMPLIANCE_AGENT_TOKEN", "")
AGENT_SERVICE_USER_ID = os.environ.get("COMPLIANCE_AGENT_USER_ID", "compliance-agent")
# compliance_manager (not compliance_analyst) because assign_reviewer below calls
# POST /reviews/{case_id}/assign, which is manager-only -- see app/main.py.
AGENT_SERVICE_ROLE = os.environ.get("COMPLIANCE_AGENT_ROLE", "compliance_manager")


def _headers() -> dict:
    if AGENT_SERVICE_TOKEN:
        return {"Authorization": f"Bearer {AGENT_SERVICE_TOKEN}"}

    return {"X-User-Id": AGENT_SERVICE_USER_ID, "X-User-Role": AGENT_SERVICE_ROLE}


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, headers=_headers(), timeout=15.0)


# ---------------------------------------------------------------------------
# Tool implementations -- each maps 1:1 to an existing endpoint
# ---------------------------------------------------------------------------

def get_active_rules() -> dict:
    """GET /rules -- fetch every current, versioned procurement control."""
    with _client() as c:
        r = c.get("/rules")
        r.raise_for_status()
        return r.json()


def evaluate_transaction(payload: dict) -> dict:
    """
    POST /evaluate -- run the deterministic risk/escalation engine on a structured
    vendor transaction. This is the ONLY source of truth for risk_band and decision.
    The agent must never state or estimate either itself.

    Expected payload shape (VendorTransaction, see app/models.py) -- at minimum:
    {
        "case_id": "...", "transaction_id": "...", "control_id": "PROC-SPEND-APPROVAL-001",
        "vendor_name": "...", "requestor_role": "...", "amount": 0, "currency": "USD",
        "business_justification": "..."
    }
    Plus whatever control-specific evidence fields apply (approval_record,
    vendor_screening_record, gift_recipient_type, vendor_payment_details_changed, etc.)
    """
    with _client() as c:
        r = c.post("/evaluate", json=payload)
        r.raise_for_status()
        return r.json()


def get_open_reviews() -> dict:
    """GET /reviews/queue -- active cases currently requiring review action."""
    with _client() as c:
        r = c.get("/reviews/queue")
        r.raise_for_status()
        return r.json()


def get_decision(case_id: str) -> dict:
    """GET /decisions/{case_id} -- retrieve a prior compliance decision."""
    with _client() as c:
        r = c.get(f"/decisions/{case_id}")
        r.raise_for_status()
        return r.json()


def assign_reviewer(case_id: str, reviewer_id: str) -> dict:
    """
    POST /reviews/{case_id}/assign -- assign a reviewer. Manager-only on the API
    side regardless of what role calls this tool.

    NOTE: For HIGH/CRITICAL risk, this should require human confirmation before
    being called -- see orchestrator.py's _blocked_tool_call() gate. Do not let the
    agent call this autonomously for high-risk cases.
    """
    with _client() as c:
        r = c.post(f"/reviews/{case_id}/assign", json={"reviewer_id": reviewer_id})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Anthropic tool-use schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_active_rules",
        "description": (
            "Fetch every current, versioned procurement control catalog (spend "
            "approval, vendor due diligence, jurisdiction, conflict of interest, "
            "expense receipts, part-time contract classification, gifts and "
            "hospitality, payment-change verification). Call this first to ground "
            "your reasoning in the current rule definitions and their control_id "
            "values, rather than assuming them."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "evaluate_transaction",
        "description": (
            "Submit a structured vendor transaction to the deterministic "
            "compliance evaluation engine. Returns the authoritative decision "
            "(approved/blocked/insufficient_evidence/human_review_required) and "
            "risk band (low/medium/high/critical). This is the ONLY source of "
            "truth for risk -- never state a risk band or decision that didn't "
            "come from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "transaction_id": {"type": "string"},
                "control_id": {
                    "type": "string",
                    "description": "One of the control_id values returned by get_active_rules.",
                },
                "vendor_name": {"type": "string"},
                "requestor_role": {"type": "string"},
                "amount": {"type": "number"},
                "currency": {"type": "string"},
                "business_justification": {"type": "string"},
                "evidence": {
                    "type": "object",
                    "description": (
                        "Any control-specific evidence fields the rule's required_evidence "
                        "calls for (e.g. approval_record, vendor_screening_record, "
                        "conflict_of_interest_record, receipt_record, "
                        "misclassification_assessment_record, payment_change_verification_record), "
                        "merged into the top-level payload."
                    ),
                },
            },
            "required": ["case_id", "transaction_id", "control_id", "vendor_name", "amount", "currency"],
        },
    },
    {
        "name": "get_open_reviews",
        "description": "List active cases currently in the review queue.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "assign_reviewer",
        "description": (
            "Assign a reviewer to a case. For HIGH/CRITICAL risk cases, this call "
            "will be blocked unless a human has already confirmed the assignment "
            "-- propose the assignment in your response instead of calling this "
            "tool directly for those cases."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "reviewer_id": {"type": "string"},
            },
            "required": ["case_id", "reviewer_id"],
        },
    },
]


def _evaluate_transaction_tool(**kwargs) -> dict:
    evidence = kwargs.pop("evidence", {}) or {}
    payload = {**kwargs, **evidence}
    return evaluate_transaction(payload)


TOOL_IMPLEMENTATIONS = {
    "get_active_rules": lambda **kw: get_active_rules(),
    "evaluate_transaction": lambda **kw: _evaluate_transaction_tool(**kw),
    "get_open_reviews": lambda **kw: get_open_reviews(),
    "assign_reviewer": lambda **kw: assign_reviewer(kw["case_id"], kw["reviewer_id"]),
}
