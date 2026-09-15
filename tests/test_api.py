import sqlite3
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import get_db_path, get_decision, save_decision, set_db_path


def _auth_headers(user_id: str, role: str) -> dict[str, str]:
    secret = os.environ["COMPLIANCE_AUTH_SECRET"]
    issuer = os.environ["COMPLIANCE_AUTH_ISSUER"]
    audience = os.environ["COMPLIANCE_AUTH_AUDIENCE"]
    token = jwt.encode(
        {
            "sub": user_id,
            "role": role,
            "iss": issuer,
            "aud": audience,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        secret,
        algorithm="HS256",
        headers={"kid": "test-key-1"},
    )

    return {
        "Authorization": f"Bearer {token}",
    }


@pytest.fixture(autouse=True)
def _configure_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLIANCE_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("COMPLIANCE_AUTH_KEYS_JSON", '{"test-key-1":"test-secret-key","test-key-2":"rotated-secret"}')
    monkeypatch.setenv("COMPLIANCE_AUTH_ISSUER", "compliance-auth")
    monkeypatch.setenv("COMPLIANCE_AUTH_AUDIENCE", "compliance-api")
    monkeypatch.delenv("COMPLIANCE_ALLOW_INSECURE_HEADERS", raising=False)


def _seed_review_case(client: TestClient, case_id: str = "case-review-1") -> None:
    # Amount above the single-approval threshold with no approval record attached
    # is guaranteed to come back insufficient_evidence / review_required=True.
    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": case_id,
            "transaction_id": f"po-{case_id}",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Test Vendor Co",
            "requestor_role": "employee",
            "amount": 2500,
            "currency": "USD",
            "business_justification": "Recurring services contract.",
        },
    )
    assert response.status_code == 200


def test_evaluate_requires_auth_token(tmp_path: Path) -> None:
    set_db_path(tmp_path / "auth.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        json={
            "case_id": "case-auth-1",
            "transaction_id": "po-auth-1",
            "vendor_name": "Test Vendor Co",
            "requestor_role": "employee",
            "amount": 40,
            "currency": "USD",
            "business_justification": "Small office supply purchase.",
        },
    )

    assert response.status_code == 401


def test_rejects_token_with_invalid_issuer(tmp_path: Path) -> None:
    set_db_path(tmp_path / "auth-invalid-issuer.db")
    client = TestClient(app)

    bad_token = jwt.encode(
        {
            "sub": "employee-1",
            "role": "employee",
            "iss": "wrong-issuer",
            "aud": os.environ["COMPLIANCE_AUTH_AUDIENCE"],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        os.environ["COMPLIANCE_AUTH_SECRET"],
        algorithm="HS256",
        headers={"kid": "test-key-1"},
    )

    response = client.post(
        "/evaluate",
        headers={"Authorization": f"Bearer {bad_token}"},
        json={
            "case_id": "case-auth-invalid-issuer-1",
            "transaction_id": "po-auth-invalid-issuer-1",
            "vendor_name": "Test Vendor Co",
            "requestor_role": "employee",
            "amount": 40,
            "currency": "USD",
            "business_justification": "Small office supply purchase.",
        },
    )

    assert response.status_code == 401


def test_review_assignment_requires_manager_role(tmp_path: Path) -> None:
    set_db_path(tmp_path / "manager.db")
    client = TestClient(app)
    _seed_review_case(client, case_id="case-manager-1")

    response = client.post(
        "/reviews/case-manager-1/assign",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={"reviewer_id": "analyst-1"},
    )

    assert response.status_code == 403


def test_review_lifecycle_preserves_decision_and_review_history(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    set_db_path(db_path)
    client = TestClient(app)
    _seed_review_case(client, case_id="case-history-1")

    assign_response = client.post(
        "/reviews/case-history-1/assign",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={"reviewer_id": "analyst-1"},
    )
    assert assign_response.status_code == 200

    start_response = client.post(
        "/reviews/case-history-1/start",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={"reviewer_id": "analyst-1"},
    )
    assert start_response.status_code == 200

    submit_response = client.post(
        "/reviews/case-history-1",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={
            "reviewer_id": "analyst-1",
            "outcome": "overridden",
            "final_decision": "approved",
            "notes": "Approval obtained out-of-band and confirmed with the vendor.",
        },
    )
    assert submit_response.status_code == 200

    with sqlite3.connect(get_db_path()) as connection:
        decision_history_count = connection.execute(
            "SELECT COUNT(*) FROM decision_history WHERE case_id = ?",
            ("case-history-1",),
        ).fetchone()[0]
        review_history_count = connection.execute(
            "SELECT COUNT(*) FROM review_history WHERE case_id = ?",
            ("case-history-1",),
        ).fetchone()[0]

    assert decision_history_count == 4
    assert review_history_count == 1


def test_reports_summary_counts_completed_reviews_and_overrides(tmp_path: Path) -> None:
    set_db_path(tmp_path / "report.db")
    client = TestClient(app)
    _seed_review_case(client, case_id="case-report-1")

    client.post(
        "/reviews/case-report-1/assign",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={"reviewer_id": "analyst-1"},
    )
    client.post(
        "/reviews/case-report-1/start",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={"reviewer_id": "analyst-1"},
    )
    client.post(
        "/reviews/case-report-1",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={
            "reviewer_id": "analyst-1",
            "outcome": "overridden",
            "final_decision": "approved",
            "notes": "Override accepted after manual review.",
        },
    )

    response = client.get(
        "/reports/summary",
        headers=_auth_headers("auditor-1", "auditor"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_decisions"] == 1
    assert payload["completed_review_count"] == 1
    assert payload["active_review_count"] == 0
    assert payload["override_count"] == 1
    assert payload["decision_count_by_risk_band"]["low"] >= 0
    assert payload["active_review_count_by_risk_band"]["low"] >= 0
    assert payload["reopened_case_count"] == 0


def test_low_risk_case_has_no_escalation_recipients(tmp_path: Path) -> None:
    set_db_path(tmp_path / "escalation-low.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-escalation-low-1",
            "transaction_id": "po-escalation-low-1",
            "vendor_name": "Acme Office Supplies",
            "requestor_role": "office_manager",
            "amount": 450,
            "currency": "USD",
            "business_justification": "Quarterly office supply restock.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_band"] == "low"
    assert payload["escalation_recipients"] == []


def test_medium_risk_case_notifies_procurement_only(tmp_path: Path) -> None:
    set_db_path(tmp_path / "escalation-medium.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-escalation-medium-1",
            "transaction_id": "po-escalation-medium-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 500,
            "currency": "USD",
            "business_justification": "Multi-night stay for an extended client engagement.",
            "receipt_record": {"attached": True, "receipt_total": 500.0},
            "prior_flagged_transactions_12m": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_band"] == "medium"
    assert payload["escalation_recipients"] == ["procurement"]


def test_critical_due_diligence_failure_notifies_all_three_stakeholders(tmp_path: Path) -> None:
    set_db_path(tmp_path / "escalation-critical.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-escalation-critical-1",
            "transaction_id": "po-escalation-critical-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Starline Trading Co",
            "requestor_role": "procurement_lead",
            "amount": 100,
            "currency": "USD",
            "business_justification": "Routine supply order.",
            "vendor_screening_record": {"completed": True, "sanctions_check_passed": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "blocked"
    assert payload["risk_band"] == "critical"
    assert set(payload["escalation_recipients"]) == {"procurement", "legal", "finance"}


def test_dashboard_summary_counts_pending_notifications_by_recipient(tmp_path: Path) -> None:
    set_db_path(tmp_path / "escalation-dashboard.db")
    client = TestClient(app)

    client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-escalation-dashboard-medium-1",
            "transaction_id": "po-escalation-dashboard-medium-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 500,
            "currency": "USD",
            "business_justification": "Multi-night stay for an extended client engagement.",
            "receipt_record": {"attached": True, "receipt_total": 500.0},
            "prior_flagged_transactions_12m": 1,
        },
    )
    client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-escalation-dashboard-critical-1",
            "transaction_id": "po-escalation-dashboard-critical-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Starline Trading Co",
            "requestor_role": "procurement_lead",
            "amount": 100,
            "currency": "USD",
            "business_justification": "Routine supply order.",
            "vendor_screening_record": {"completed": True, "sanctions_check_passed": False},
        },
    )

    response = client.get(
        "/dashboard/summary",
        headers=_auth_headers("auditor-1", "auditor"),
    )

    assert response.status_code == 200
    payload = response.json()["pending_notifications_by_recipient"]
    assert payload["procurement"] == 2
    assert payload["legal"] == 1
    assert payload["finance"] == 1


def test_dashboard_summary_aggregates_by_control_and_signal(tmp_path: Path) -> None:
    set_db_path(tmp_path / "dashboard.db")
    client = TestClient(app)

    compliant_response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-dashboard-compliant-1",
            "transaction_id": "po-dashboard-compliant-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Acme Office Supplies",
            "requestor_role": "office_manager",
            "amount": 450,
            "currency": "USD",
            "business_justification": "Quarterly office supply restock.",
        },
    )
    assert compliant_response.status_code == 200

    missing_approval_response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-dashboard-missing-approval-1",
            "transaction_id": "po-dashboard-missing-approval-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Meridian Consulting Group",
            "requestor_role": "sales_manager",
            "amount": 2500,
            "currency": "USD",
            "business_justification": "Market research engagement.",
        },
    )
    assert missing_approval_response.status_code == 200

    denied_response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-dashboard-denied-1",
            "transaction_id": "po-dashboard-denied-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Meridian Consulting Group",
            "requestor_role": "sales_manager",
            "amount": 2500,
            "currency": "USD",
            "business_justification": "Market research engagement.",
            "approval_record": {"approver_role": "compliance_manager", "approved": False},
        },
    )
    assert denied_response.status_code == 200

    missing_screening_response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-dashboard-missing-screening-1",
            "transaction_id": "po-dashboard-missing-screening-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Novaline Freight Partners",
            "new_vendor": True,
            "requestor_role": "logistics_lead",
            "amount": 1800,
            "currency": "USD",
            "business_justification": "First shipment contract with a new freight vendor.",
        },
    )
    assert missing_screening_response.status_code == 200

    response = client.get(
        "/dashboard/summary",
        headers=_auth_headers("auditor-1", "auditor"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_decisions"] == 4
    assert payload["total_active_reviews"] == 3
    assert payload["total_blocked"] == 1
    assert payload["total_insufficient_evidence"] == 2

    controls_by_id = {control["control_id"]: control for control in payload["controls"]}
    # All five known controls should appear even if some had zero traffic.
    assert set(controls_by_id) == {
        "PROC-SPEND-APPROVAL-001",
        "PROC-VENDOR-DUEDILIGENCE-001",
        "PROC-INTL-VENDOR-001",
        "PROC-VENDOR-COI-001",
        "PROC-EXPENSE-RECEIPT-001",
    }

    spend_approval = controls_by_id["PROC-SPEND-APPROVAL-001"]
    assert spend_approval["total_decisions"] == 3
    assert spend_approval["approved_count"] == 1
    assert spend_approval["blocked_count"] == 1
    assert spend_approval["insufficient_evidence_count"] == 1
    assert spend_approval["active_review_count"] == 2

    due_diligence = controls_by_id["PROC-VENDOR-DUEDILIGENCE-001"]
    assert due_diligence["total_decisions"] == 1
    assert due_diligence["insufficient_evidence_count"] == 1

    assert controls_by_id["PROC-INTL-VENDOR-001"]["total_decisions"] == 0

    signal_counts = {signal["signal_id"]: signal["count"] for signal in payload["top_triggered_signals"]}
    assert signal_counts["SIG-MISSING-APPROVAL"] == 1
    assert signal_counts["SIG-APPROVAL-DENIED"] == 1
    assert signal_counts["SIG-MISSING-VENDOR-SCREENING"] == 1

    assert payload["queue_metrics"]["active_review_count"] == 3


def test_evaluate_missing_approval_requires_evidence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "missing-approval.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-missing-approval-1",
            "transaction_id": "po-missing-approval-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Meridian Consulting Group",
            "requestor_role": "sales_manager",
            "amount": 2500,
            "currency": "USD",
            "business_justification": "Market research engagement.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["review_required"] is True
    assert payload["review_status"] == "pending"
    assert payload["rule_metadata"]["control_id"] == "PROC-SPEND-APPROVAL-001"


def test_evaluate_missing_screening_requires_evidence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "missing-screening.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-missing-screening-1",
            "transaction_id": "po-missing-screening-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Novaline Freight Partners",
            "new_vendor": True,
            "requestor_role": "logistics_lead",
            "amount": 1800,
            "currency": "USD",
            "business_justification": "First shipment contract with a new freight vendor.",
            "approval_record": {"approver_role": "compliance_manager", "approved": True},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["review_required"] is True
    assert "SIG-MISSING-VENDOR-SCREENING" in payload["triggered_signal_ids"]


def test_denied_approval_blocks_transaction(tmp_path: Path) -> None:
    set_db_path(tmp_path / "denied-approval.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-denied-approval-1",
            "transaction_id": "po-denied-approval-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Meridian Consulting Group",
            "requestor_role": "sales_manager",
            "amount": 2500,
            "currency": "USD",
            "business_justification": "Market research engagement.",
            "approval_record": {"approver_role": "compliance_manager", "approved": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "blocked"
    assert payload["risk_band"] == "critical"
    assert payload["review_required"] is True


def test_vendor_screening_failure_blocks_transaction(tmp_path: Path) -> None:
    set_db_path(tmp_path / "failed-screening.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-failed-screening-1",
            "transaction_id": "po-failed-screening-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Starline Trading Co",
            "new_vendor": True,
            "vendor_risk_level": "high",
            "requestor_role": "procurement_lead",
            "amount": 12000,
            "currency": "USD",
            "business_justification": "Bulk hardware procurement from an overseas supplier.",
            "vendor_screening_record": {"completed": True, "sanctions_check_passed": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "blocked"
    assert payload["risk_band"] == "critical"
    assert "SIG-SANCTIONS-SCREENING-FAILED" in payload["triggered_signal_ids"]


def test_dual_approval_threshold_requires_second_approval(tmp_path: Path) -> None:
    set_db_path(tmp_path / "dual-approval.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-dual-approval-1",
            "transaction_id": "po-dual-approval-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Kestrel Manufacturing",
            "requestor_role": "operations_manager",
            "amount": 15000,
            "currency": "USD",
            "business_justification": "Custom tooling order for the new production line.",
            "approval_record": {"approver_role": "compliance_manager", "approved": True},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "human_review_required"
    assert payload["review_required"] is True
    assert "SIG-SECOND-APPROVAL-NEEDED" in payload["triggered_signal_ids"]


def test_risk_signals_keep_low_risk_compliant_case_auto_closed(tmp_path: Path) -> None:
    set_db_path(tmp_path / "risk-low.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-risk-low-1",
            "transaction_id": "po-risk-low-1",
            "control_id": "PROC-SPEND-APPROVAL-001",
            "vendor_name": "Acme Office Supplies",
            "vendor_risk_level": "low",
            "requestor_role": "office_manager",
            "amount": 450,
            "currency": "USD",
            "business_justification": "Quarterly office supply restock.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is False
    assert payload["risk_band"] == "low"
    assert payload["escalation_decision"] == "auto_close"


def test_risk_signals_route_approved_case_to_mandatory_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "risk-high.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-risk-high-1",
            "transaction_id": "po-risk-high-1",
            "control_id": "PROC-VENDOR-DUEDILIGENCE-001",
            "vendor_name": "Orion Field Services",
            "vendor_risk_level": "high",
            "requestor_role": "regional_manager",
            "amount": 900,
            "currency": "USD",
            "business_justification": "Recurring maintenance contract renewal.",
            "approval_record": {"approver_role": "compliance_manager", "approved": True},
            "vendor_screening_record": {"completed": True, "sanctions_check_passed": True},
            "prior_flagged_transactions_12m": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is True
    assert payload["risk_band"] in ("high", "critical")
    assert payload["escalation_decision"] == "queue_for_review"


def test_reopen_completed_review_creates_new_cycle_and_tracks_reason(tmp_path: Path) -> None:
    db_path = tmp_path / "reopen.db"
    set_db_path(db_path)
    client = TestClient(app)
    _seed_review_case(client, case_id="case-reopen-1")

    assign_response = client.post(
        "/reviews/case-reopen-1/assign",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={"reviewer_id": "analyst-1"},
    )
    assert assign_response.status_code == 200

    start_response = client.post(
        "/reviews/case-reopen-1/start",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={"reviewer_id": "analyst-1"},
    )
    assert start_response.status_code == 200

    submit_response = client.post(
        "/reviews/case-reopen-1",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={
            "reviewer_id": "analyst-1",
            "outcome": "approved",
            "final_decision": "approved",
            "notes": "Initial review complete.",
        },
    )
    assert submit_response.status_code == 200

    reopen_response = client.post(
        "/reviews/case-reopen-1/reopen",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={
            "reason": "new_evidence",
            "notes": "New supporting documents require reassessment.",
        },
    )

    assert reopen_response.status_code == 200
    payload = reopen_response.json()
    assert payload["review_status"] == "reopened"
    assert payload["review_required"] is True
    assert payload["review_cycle_id"] == 2
    assert payload["reopen_reason"] == "new_evidence"
    assert payload["final_reviewer_outcome"] is None

    with sqlite3.connect(get_db_path()) as connection:
        decision_history_count = connection.execute(
            "SELECT COUNT(*) FROM decision_history WHERE case_id = ?",
            ("case-reopen-1",),
        ).fetchone()[0]

    assert decision_history_count == 5


def test_review_metrics_counts_pending_assigned_and_in_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "metrics.db")
    client = TestClient(app)

    _seed_review_case(client, case_id="case-metrics-pending")
    _seed_review_case(client, case_id="case-metrics-assigned")
    _seed_review_case(client, case_id="case-metrics-in-review")

    assign_response = client.post(
        "/reviews/case-metrics-assigned/assign",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={"reviewer_id": "analyst-1"},
    )
    assert assign_response.status_code == 200

    assign_and_start_response = client.post(
        "/reviews/case-metrics-in-review/assign",
        headers=_auth_headers("manager-1", "compliance_manager"),
        json={"reviewer_id": "analyst-1"},
    )
    assert assign_and_start_response.status_code == 200

    start_response = client.post(
        "/reviews/case-metrics-in-review/start",
        headers=_auth_headers("analyst-1", "compliance_analyst"),
        json={"reviewer_id": "analyst-1"},
    )
    assert start_response.status_code == 200

    metrics_response = client.get(
        "/reviews/metrics",
        headers=_auth_headers("auditor-1", "auditor"),
    )

    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["active_review_count"] == 3
    assert payload["pending_count"] == 1
    assert payload["assigned_count"] == 1
    assert payload["in_review_count"] == 1
    assert payload["reopened_count"] == 0
    assert payload["breached_sla_count"] == 0
    assert payload["active_by_risk_band"]["high"] >= 0
    assert payload["breached_sla_by_risk_band"]["high"] >= 0
    assert payload["average_queue_age_hours"] >= 0
    assert payload["oldest_queue_age_hours"] >= 0


def test_evaluate_missing_screening_for_high_risk_jurisdiction(tmp_path: Path) -> None:
    set_db_path(tmp_path / "jurisdiction-missing-screening.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-jurisdiction-missing-screening-1",
            "transaction_id": "po-jurisdiction-missing-screening-1",
            "control_id": "PROC-INTL-VENDOR-001",
            "vendor_name": "Baltic Components LLC",
            "new_vendor": True,
            "requestor_role": "procurement_lead",
            "amount": 1200,
            "currency": "USD",
            "country_code": "RU",
            "business_justification": "Specialty electronic components sourcing.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["review_required"] is True
    assert "SIG-MISSING-VENDOR-SCREENING" in payload["triggered_signal_ids"]


def test_high_risk_jurisdiction_requires_enhanced_due_diligence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "jurisdiction-missing-edd.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-jurisdiction-missing-edd-1",
            "transaction_id": "po-jurisdiction-missing-edd-1",
            "control_id": "PROC-INTL-VENDOR-001",
            "vendor_name": "Baltic Components LLC",
            "new_vendor": True,
            "requestor_role": "procurement_lead",
            "amount": 1200,
            "currency": "USD",
            "country_code": "RU",
            "business_justification": "Specialty electronic components sourcing.",
            "vendor_screening_record": {
                "completed": True,
                "sanctions_check_passed": True,
                "enhanced_due_diligence_completed": False,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "human_review_required"
    assert payload["review_required"] is True
    assert "SIG-ENHANCED-DD-REQUIRED" in payload["triggered_signal_ids"]


def test_high_risk_jurisdiction_compliant_still_routes_to_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "jurisdiction-compliant.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-jurisdiction-compliant-1",
            "transaction_id": "po-jurisdiction-compliant-1",
            "control_id": "PROC-INTL-VENDOR-001",
            "vendor_name": "Baltic Components LLC",
            "new_vendor": True,
            "requestor_role": "procurement_lead",
            "amount": 1200,
            "currency": "USD",
            "country_code": "RU",
            "business_justification": "Specialty electronic components sourcing.",
            "vendor_screening_record": {
                "completed": True,
                "sanctions_check_passed": True,
                "enhanced_due_diligence_completed": True,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is True
    assert payload["risk_band"] in ("high", "critical")
    assert payload["escalation_decision"] == "queue_for_review"


def test_low_risk_jurisdiction_auto_closes(tmp_path: Path) -> None:
    set_db_path(tmp_path / "jurisdiction-low-risk.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-jurisdiction-low-risk-1",
            "transaction_id": "po-jurisdiction-low-risk-1",
            "control_id": "PROC-INTL-VENDOR-001",
            "vendor_name": "Alpine Precision Tools",
            "requestor_role": "procurement_lead",
            "amount": 800,
            "currency": "USD",
            "country_code": "CH",
            "business_justification": "Standard tooling order from an established EU vendor.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is False
    assert payload["risk_band"] == "low"
    assert payload["escalation_decision"] == "auto_close"


def test_evaluate_missing_coi_disclosure_requires_evidence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "coi-missing-disclosure.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-coi-missing-disclosure-1",
            "transaction_id": "po-coi-missing-disclosure-1",
            "control_id": "PROC-VENDOR-COI-001",
            "vendor_name": "Harborview Design Studio",
            "requestor_role": "marketing_manager",
            "amount": 3200,
            "currency": "USD",
            "business_justification": "Brand refresh design work.",
            "potential_conflict_of_interest": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["review_required"] is True
    assert "SIG-MISSING-COI-DISCLOSURE" in payload["triggered_signal_ids"]


def test_coi_pending_clearance_requires_human_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "coi-pending.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-coi-pending-1",
            "transaction_id": "po-coi-pending-1",
            "control_id": "PROC-VENDOR-COI-001",
            "vendor_name": "Harborview Design Studio",
            "requestor_role": "marketing_manager",
            "amount": 3200,
            "currency": "USD",
            "business_justification": "Brand refresh design work.",
            "potential_conflict_of_interest": True,
            "conflict_of_interest_record": {"disclosed": True, "cleared": None},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "human_review_required"
    assert payload["review_required"] is True
    assert "SIG-COI-REVIEW-PENDING" in payload["triggered_signal_ids"]


def test_coi_rejected_by_compliance_blocks_transaction(tmp_path: Path) -> None:
    set_db_path(tmp_path / "coi-rejected.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-coi-rejected-1",
            "transaction_id": "po-coi-rejected-1",
            "control_id": "PROC-VENDOR-COI-001",
            "vendor_name": "Harborview Design Studio",
            "requestor_role": "marketing_manager",
            "amount": 3200,
            "currency": "USD",
            "business_justification": "Brand refresh design work.",
            "potential_conflict_of_interest": True,
            "conflict_of_interest_record": {"disclosed": True, "cleared": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "blocked"
    assert payload["risk_band"] == "critical"
    assert "SIG-COI-REJECTED" in payload["triggered_signal_ids"]


def test_coi_cleared_by_compliance_still_routes_to_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "coi-cleared.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-coi-cleared-1",
            "transaction_id": "po-coi-cleared-1",
            "control_id": "PROC-VENDOR-COI-001",
            "vendor_name": "Harborview Design Studio",
            "requestor_role": "marketing_manager",
            "amount": 3200,
            "currency": "USD",
            "business_justification": "Brand refresh design work.",
            "potential_conflict_of_interest": True,
            "conflict_of_interest_record": {"disclosed": True, "cleared": True},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is True
    assert payload["risk_band"] in ("high", "critical")
    assert payload["escalation_decision"] == "queue_for_review"


def test_no_flagged_coi_auto_closes(tmp_path: Path) -> None:
    set_db_path(tmp_path / "coi-not-flagged.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-coi-not-flagged-1",
            "transaction_id": "po-coi-not-flagged-1",
            "control_id": "PROC-VENDOR-COI-001",
            "vendor_name": "Acme Office Supplies",
            "requestor_role": "office_manager",
            "amount": 450,
            "currency": "USD",
            "business_justification": "Quarterly office supply restock.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is False
    assert payload["risk_band"] == "low"
    assert payload["escalation_decision"] == "auto_close"


def test_evaluate_missing_receipt_requires_evidence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "receipt-missing.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-receipt-missing-1",
            "transaction_id": "po-receipt-missing-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 120,
            "currency": "USD",
            "business_justification": "One-night stay for a client site visit.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["risk_band"] == "medium"
    assert payload["review_required"] is True
    assert "SIG-MISSING-RECEIPT" in payload["triggered_signal_ids"]


def test_receipt_amount_mismatch_requires_human_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "receipt-mismatch.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-receipt-mismatch-1",
            "transaction_id": "po-receipt-mismatch-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 120,
            "currency": "USD",
            "business_justification": "One-night stay for a client site visit.",
            "receipt_record": {"attached": True, "receipt_total": 45.0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "human_review_required"
    assert payload["risk_band"] == "high"
    assert "SIG-RECEIPT-AMOUNT-MISMATCH" in payload["triggered_signal_ids"]


def test_receipt_matched_case_auto_closes(tmp_path: Path) -> None:
    set_db_path(tmp_path / "receipt-matched.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-receipt-matched-1",
            "transaction_id": "po-receipt-matched-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 80,
            "currency": "USD",
            "business_justification": "One-night stay for a client site visit.",
            "receipt_record": {"attached": True, "receipt_total": 80.0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is False
    assert payload["risk_band"] == "low"
    assert payload["escalation_decision"] == "auto_close"


def test_receipt_matched_with_prior_flag_routes_to_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "receipt-flagged.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-receipt-flagged-1",
            "transaction_id": "po-receipt-flagged-1",
            "control_id": "PROC-EXPENSE-RECEIPT-001",
            "vendor_name": "Riverside Hotel",
            "requestor_role": "account_executive",
            "amount": 500,
            "currency": "USD",
            "business_justification": "Multi-night stay for an extended client engagement.",
            "receipt_record": {"attached": True, "receipt_total": 500.0},
            "prior_flagged_transactions_12m": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["review_required"] is True
    assert payload["risk_band"] == "medium"
    assert payload["escalation_decision"] == "queue_for_review"


def test_review_metrics_counts_sla_breach_for_aged_case(tmp_path: Path) -> None:
    set_db_path(tmp_path / "metrics-sla.db")
    client = TestClient(app)

    _seed_review_case(client, case_id="case-metrics-sla")

    decision = get_decision("case-metrics-sla")
    assert decision is not None

    aged_decision = decision.model_copy(
        update={
            "evaluated_at": (datetime.now(UTC) - timedelta(hours=30)).isoformat(),
        }
    )
    save_decision(aged_decision, event_type="decision_backdated_for_test", actor_id="test", actor_role="test")

    metrics_response = client.get(
        "/reviews/metrics",
        headers=_auth_headers("auditor-1", "auditor"),
    )

    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["active_review_count"] == 1
    assert payload["breached_sla_count"] == 1
    assert payload["oldest_queue_age_hours"] >= 30
    assert sum(payload["active_by_risk_band"].values()) == payload["active_review_count"]
    assert sum(payload["breached_sla_by_risk_band"].values()) == payload["breached_sla_count"]
