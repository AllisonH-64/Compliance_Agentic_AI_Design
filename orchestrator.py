"""
Orchestrator for the Vendor Due-Diligence Gate's LLM triage agent.

Responsibilities:
  1. Runs a Claude tool-use loop over an incoming raw transaction description.
  2. Never lets the model compute or override risk -- that stays entirely inside
     evaluate_transaction() / the deterministic engine (app/engine.py).
  3. Blocks autonomous HIGH/CRITICAL reviewer assignment pending human confirmation.
  4. Writes every tool call + the model's rationale to an append-only agent decision
     log, separate from (but linked to) the existing compliance decision/audit tables.

This is intentionally a single-agent tool-use loop rather than a multi-agent
framework -- for an auditable compliance workflow, a single reasoning loop with
well-scoped tools is easier to log, review, and reason about than a multi-agent
graph.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import anthropic

from tools import TOOL_SCHEMAS, TOOL_IMPLEMENTATIONS

DEFAULT_MODEL = "claude-sonnet-5"
MODEL = os.environ.get("COMPLIANCE_AGENT_MODEL", DEFAULT_MODEL)
MAX_TOOL_TURNS = 6

# RiskBand values (app/models.py) are lowercase strings -- "low"/"medium"/"high"/"critical".
HIGH_RISK_BANDS = {"high", "critical"}

SYSTEM_PROMPT = """You are a compliance triage assistant supporting the \
Vendor Due-Diligence Gate. You help analysts by:

1. Extracting structured vendor-transaction fields from a raw description.
2. Calling evaluate_transaction to get the AUTHORITATIVE decision and risk band. \
You never state, imply, or estimate a decision or risk band yourself -- it must \
come from that tool's response.
3. Explaining your reasoning in plain language so it can be stored as part of \
the audit record.
4. Proposing next steps (reviewer assignment, escalation to Legal/Finance/ \
Procurement, requesting more evidence). For HIGH or CRITICAL risk cases, you \
propose the assignment and explain why, but do not call assign_reviewer \
yourself -- a human compliance manager must confirm it first.

If a transaction description is missing information evaluate_transaction needs \
(e.g. which control applies, required evidence for that control), ask a \
clarifying question rather than guessing.

Always ground your control references in the output of get_active_rules rather \
than assumed knowledge of the eight controls.
"""


def _log_path() -> str:
    return os.environ.get("AGENT_LOG_PATH", "agent_decision_log.jsonl")


def _append_log(entry: dict) -> None:
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(_log_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")


def _blocked_tool_call(tool_name: str, tool_input: dict) -> bool:
    """
    Gate autonomous actions on HIGH/CRITICAL cases. Requires the caller to have
    already run evaluate_transaction and to be tracking the last known risk band
    for this case_id -- see run_agent() below for the simple in-session tracking
    used here.
    """
    return tool_name == "assign_reviewer"


def run_agent(transaction_description: str, submitted_by: str) -> dict:
    """
    Run the agent over a raw transaction description.

    Returns a dict with the final assistant message, the full tool-call trace, and
    a flag indicating whether human confirmation is pending before any reviewer
    assignment can proceed.
    """
    client = anthropic.Anthropic()
    session_id = str(uuid.uuid4())

    messages = [{"role": "user", "content": transaction_description}]
    trace = []
    last_risk_band = None
    pending_human_confirmation = None

    for turn in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            final_text = "".join(
                b.text for b in response.content if b.type == "text"
            )
            _append_log({
                "session_id": session_id,
                "submitted_by": submitted_by,
                "event": "agent_final_response",
                "text": final_text,
                "last_risk_band": last_risk_band,
                "trace": trace,
            })
            return {
                "session_id": session_id,
                "response": final_text,
                "risk_band": last_risk_band,
                "pending_human_confirmation": pending_human_confirmation,
                "trace": trace,
            }

        tool_results = []
        for block in tool_use_blocks:
            tool_name = block.name
            tool_input = block.input

            if _blocked_tool_call(tool_name, tool_input) and last_risk_band in HIGH_RISK_BANDS:
                result = {
                    "status": "blocked",
                    "reason": (
                        f"{tool_name} requires human confirmation for "
                        f"{last_risk_band} risk cases. "
                        "Escalate to a compliance_manager for sign-off."
                    ),
                }
                pending_human_confirmation = {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "risk_band": last_risk_band,
                }
            else:
                try:
                    result = TOOL_IMPLEMENTATIONS[tool_name](**tool_input)
                    if tool_name == "evaluate_transaction":
                        last_risk_band = result.get("risk_band")
                except Exception as e:
                    result = {"status": "error", "error": str(e)}

            trace.append({
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": result,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    _append_log({
        "session_id": session_id,
        "submitted_by": submitted_by,
        "event": "max_turns_exceeded",
        "trace": trace,
    })
    return {
        "session_id": session_id,
        "response": "Agent did not reach a final answer within the turn limit -- routing to human review.",
        "risk_band": last_risk_band,
        "pending_human_confirmation": pending_human_confirmation,
        "trace": trace,
    }
