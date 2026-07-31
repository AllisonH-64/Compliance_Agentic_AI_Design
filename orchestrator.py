"""
Orchestrator for the Employee Conduct Compliance Agent.

Responsibilities:
  1. Runs a Claude tool-use loop over an incoming incident report.
  2. Never lets the model compute or override severity — that stays
     entirely inside evaluate_incident() / the deterministic engine.
  3. Blocks autonomous HIGH/CRITICAL actions pending human confirmation.
  4. Writes every tool call + the model's rationale to an append-only
     agent decision log, separate from (but linked to) your existing
     compliance decision/audit tables.

This is intentionally a single-agent tool-use loop rather than a
multi-agent framework — for an auditable compliance workflow, a
single reasoning loop with well-scoped tools is easier to log,
review, and reason about than a multi-agent graph.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import anthropic

from tools import TOOL_SCHEMAS, TOOL_IMPLEMENTATIONS

MODEL = "claude-sonnet-4-6"
MAX_TOOL_TURNS = 6

HIGH_SEVERITY_BANDS = {"HIGH", "CRITICAL"}

SYSTEM_PROMPT = """You are a compliance triage assistant supporting the \
Employee Conduct Compliance program. You help analysts by:

1. Extracting structured fields from raw incident reports.
2. Calling evaluate_incident to get the AUTHORITATIVE severity band and \
escalation requirement. You never state, imply, or estimate a severity \
band yourself — it must come from that tool's response.
3. Explaining your reasoning in plain language so it can be stored as \
part of the audit record.
4. Proposing next steps (investigator assignment, escalation to Legal/HR, \
requesting more information). For HIGH or CRITICAL severity cases, you \
propose the action and explain why, but do not call assign_investigator \
yourself — a human compliance manager must confirm it first.

If a report is missing information needed for evaluate_incident (e.g. \
jurisdiction, whether protected characteristics are involved), ask a \
clarifying question rather than guessing.

Always ground your rule references in the output of get_active_rules \
rather than assumed knowledge of the four controls.
"""


def _log_path() -> str:
    return os.environ.get("AGENT_LOG_PATH", "agent_decision_log.jsonl")


def _append_log(entry: dict) -> None:
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(_log_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")


def _blocked_tool_call(tool_name: str, tool_input: dict) -> bool:
    """
    Gate autonomous actions on HIGH/CRITICAL cases. Requires the caller
    to have already run evaluate_incident and to be tracking the last
    known severity band for this case_id — see run_agent() below for
    the simple in-session tracking used here.
    """
    return tool_name == "assign_investigator"


def run_agent(incident_report_text: str, submitted_by: str) -> dict:
    """
    Run the agent over a raw incident report.

    Returns a dict with the final assistant message, the full tool-call
    trace, and a flag indicating whether human confirmation is pending
    before any investigator assignment can proceed.
    """
    client = anthropic.Anthropic()
    session_id = str(uuid.uuid4())

    messages = [{"role": "user", "content": incident_report_text}]
    trace = []
    last_severity_band = None
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
                "last_severity_band": last_severity_band,
                "trace": trace,
            })
            return {
                "session_id": session_id,
                "response": final_text,
                "severity_band": last_severity_band,
                "pending_human_confirmation": pending_human_confirmation,
                "trace": trace,
            }

        tool_results = []
        for block in tool_use_blocks:
            tool_name = block.name
            tool_input = block.input

            if _blocked_tool_call(tool_name, tool_input) and last_severity_band in HIGH_SEVERITY_BANDS:
                result = {
                    "status": "blocked",
                    "reason": (
                        f"{tool_name} requires human confirmation for "
                        f"{last_severity_band} severity cases. "
                        "Escalate to a compliance_manager for sign-off."
                    ),
                }
                pending_human_confirmation = {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "severity_band": last_severity_band,
                }
            else:
                try:
                    result = TOOL_IMPLEMENTATIONS[tool_name](**tool_input)
                    if tool_name == "evaluate_incident":
                        last_severity_band = result.get("severity_band") or result.get("severity")
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
        "response": "Agent did not reach a final answer within the turn limit — routing to human review.",
        "severity_band": last_severity_band,
        "pending_human_confirmation": pending_human_confirmation,
        "trace": trace,
    }
