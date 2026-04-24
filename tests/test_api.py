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
    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": case_id,
            "transaction_id": f"txn-{case_id}",
            "control_id": "ETH-GIFT-001",
            "amount": 200,
            "currency": "USD",
            "requestor_role": "sales_manager",
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
            "transaction_id": "txn-auth-1",
            "amount": 40,
            "currency": "USD",
            "requestor_role": "employee",
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
            "transaction_id": "txn-auth-invalid-issuer-1",
            "amount": 40,
            "currency": "USD",
            "requestor_role": "employee",
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
            "final_decision": "compliant",
            "notes": "Manager-approved exception recorded.",
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
            "final_decision": "compliant",
            "notes": "Override accepted after review.",
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


def test_evaluate_receipt_control_requires_receipt_evidence(tmp_path: Path) -> None:
    set_db_path(tmp_path / "receipt.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-receipt-1",
            "transaction_id": "txn-receipt-1",
            "control_id": "ETH-GIFT-002",
            "amount": 120,
            "currency": "USD",
            "requestor_role": "employee",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "insufficient_evidence"
    assert payload["review_required"] is True
    assert payload["review_status"] == "pending"
    assert payload["rule_metadata"]["control_id"] == "ETH-GIFT-002"


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
    assert payload["active_by_risk_band"]["medium"] >= 0
    assert payload["breached_sla_by_risk_band"]["medium"] >= 0
    assert payload["average_queue_age_hours"] >= 0
    assert payload["oldest_queue_age_hours"] >= 0


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


def test_risk_signals_keep_low_risk_compliant_case_auto_closed(tmp_path: Path) -> None:
    set_db_path(tmp_path / "risk-low.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-risk-low-1",
            "transaction_id": "txn-risk-low-1",
            "control_id": "ETH-GIFT-001",
            "amount": 60,
            "currency": "USD",
            "requestor_role": "employee",
            "recipient_type": "vendor",
            "country_code": "US",
            "market_risk_level": "low",
            "business_purpose": "Client working lunch",
            "prior_interactions_12m": 1,
            "event_context": "relationship_management",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "compliant"
    assert payload["review_required"] is False
    assert payload["risk_band"] == "low"
    assert payload["escalation_decision"] == "auto_close"


def test_risk_signals_route_compliant_case_to_mandatory_review(tmp_path: Path) -> None:
    set_db_path(tmp_path / "risk-high.db")
    client = TestClient(app)

    response = client.post(
        "/evaluate",
        headers=_auth_headers("employee-1", "employee"),
        json={
            "case_id": "case-risk-high-1",
            "transaction_id": "txn-risk-high-1",
            "control_id": "ETH-GIFT-001",
            "amount": 80,
            "currency": "USD",
            "requestor_role": "employee",
            "recipient_type": "government_official",
            "country_code": "US",
            "market_risk_level": "high",
            "business_purpose": "Routine courtesy gift",
            "prior_interactions_12m": 2,
            "event_context": "relationship_management",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "human_review_required"
    assert payload["review_required"] is True
    assert payload["review_status"] == "pending"
    assert payload["risk_band"] in ("high", "critical")
    assert "SIG-GOV-OFFICIAL" in payload["triggered_signal_ids"]
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
            "final_decision": "compliant",
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