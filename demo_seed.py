"""Seed the local demo database with a curated, representative set of vendor
transactions and review-lifecycle actions, so the API has real, varied data to
click through for a live demo: one case touching each of the 8 controls, a full
spread of decisions (approved / blocked / insufficient_evidence /
human_review_required), and one case carried through the entire
assign -> start -> submit -> reopen lifecycle.

Usage:
    python dev_server.py          # start the API first, in one terminal
    python demo_seed.py           # then seed it, in another

For a clean run, delete data/audit.db first -- re-running without doing so just
re-evaluates the same case_ids (an upsert) and appends more review-history events.
"""

import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"

EMPLOYEE = {"X-User-Id": "demo-employee", "X-User-Role": "employee"}
ANALYST = {"X-User-Id": "analyst-1", "X-User-Role": "compliance_analyst"}
MANAGER = {"X-User-Id": "manager-1", "X-User-Role": "compliance_manager"}


def _load(fixture: str) -> dict:
    return json.loads((EXAMPLES_DIR / fixture).read_text())


def _evaluate(client: httpx.Client, fixture: str) -> dict:
    payload = _load(fixture)
    resp = client.post("/evaluate", headers=EMPLOYEE, json=payload)
    resp.raise_for_status()
    decision = resp.json()
    print(f"  {payload['case_id']:<10} {fixture:<52} -> {decision['decision']:<22} risk={decision['risk_band']}")
    return decision


def _assign(client: httpx.Client, case_id: str, reviewer_id: str = "analyst-1") -> None:
    resp = client.post(f"/reviews/{case_id}/assign", headers=MANAGER, json={"reviewer_id": reviewer_id})
    resp.raise_for_status()
    print(f"  {case_id:<10} assigned to {reviewer_id}")


def _start(client: httpx.Client, case_id: str, reviewer_id: str = "analyst-1") -> None:
    resp = client.post(f"/reviews/{case_id}/start", headers=ANALYST, json={"reviewer_id": reviewer_id})
    resp.raise_for_status()
    print(f"  {case_id:<10} review started")


def _submit(
    client: httpx.Client,
    case_id: str,
    final_decision: str,
    outcome: str,
    notes: str,
    reviewer_id: str = "analyst-1",
) -> None:
    resp = client.post(
        f"/reviews/{case_id}",
        headers=ANALYST,
        json={"reviewer_id": reviewer_id, "outcome": outcome, "final_decision": final_decision, "notes": notes},
    )
    resp.raise_for_status()
    print(f"  {case_id:<10} review submitted -> {final_decision}")


def _reopen(client: httpx.Client, case_id: str, reason: str, notes: str) -> None:
    resp = client.post(f"/reviews/{case_id}/reopen", headers=MANAGER, json={"reason": reason, "notes": notes})
    resp.raise_for_status()
    print(f"  {case_id:<10} reopened ({reason})")


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.ConnectError:
            print(f"Could not reach {BASE_URL} -- start the API first (python dev_server.py).", file=sys.stderr)
            sys.exit(1)

        print("Evaluating transactions across all 8 controls...")
        _evaluate(client, "vendor_transaction_compliant.json")                             # PROC-SPEND-APPROVAL-001: approved, auto-close
        _evaluate(client, "vendor_transaction_missing_approval.json")                       # PROC-SPEND-APPROVAL-001: insufficient_evidence
        _evaluate(client, "vendor_transaction_dual_approval_needed.json")                   # PROC-SPEND-APPROVAL-001: human_review_required
        _evaluate(client, "vendor_transaction_failed_screening.json")                       # PROC-VENDOR-DUEDILIGENCE-001: blocked, critical
        _evaluate(client, "vendor_transaction_high_risk_vendor.json")                       # PROC-VENDOR-DUEDILIGENCE-001: approved but reviewed
        _evaluate(client, "vendor_transaction_high_risk_jurisdiction_missing_edd.json")     # PROC-INTL-VENDOR-001: human_review_required
        _evaluate(client, "vendor_transaction_coi_pending_review.json")                     # PROC-VENDOR-COI-001: human_review_required
        _evaluate(client, "vendor_transaction_coi_cleared.json")                            # PROC-VENDOR-COI-001: approved but reviewed
        _evaluate(client, "vendor_transaction_expense_receipt_mismatch.json")               # PROC-EXPENSE-RECEIPT-001: human_review_required
        _evaluate(client, "vendor_transaction_part_time_possible_misclassification.json")   # PROC-PART-TIME-CONTRACT-001: human_review_required
        _evaluate(client, "vendor_transaction_gift_government_official_missing_approval.json")  # PROC-GIFTS-HOSPITALITY-001: insufficient_evidence, critical
        _evaluate(client, "vendor_transaction_payment_change_verification_failed.json")     # PROC-VENDOR-PAYMENT-CHANGE-001: blocked, critical

        print("\nDriving review-lifecycle actions...")
        _assign(client, "CASE-2004")                      # failed screening: assigned, awaiting analyst
        _assign(client, "CASE-2020")                       # possible misclassification: assigned
        _assign(client, "CASE-2005")
        _start(client, "CASE-2005")                        # dual approval: in review

        _assign(client, "CASE-2011")                       # COI case carries the full lifecycle
        _start(client, "CASE-2011")
        _submit(
            client,
            "CASE-2011",
            final_decision="approved",
            outcome="overridden",
            notes="Family relationship disclosed and reviewed; spend is arm's-length and reasonable. Cleared to proceed.",
        )
        _reopen(
            client,
            "CASE-2011",
            reason="audit_followup",
            notes="Quarterly COI audit sampled this case for a second look.",
        )

        print(
            "\nDone: 12 transactions across all 8 controls, with pending, assigned, "
            "in-review, completed, and reopened review states represented."
        )
        print("Try:")
        print(f"  {BASE_URL}/docs")
        print(f"  {BASE_URL}/dashboard/summary")
        print(f"  {BASE_URL}/reviews/metrics")


if __name__ == "__main__":
    main()
