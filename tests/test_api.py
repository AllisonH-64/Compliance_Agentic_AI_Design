import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.storage import get_db_path, set_db_path


def _auth_headers(user_id: str, role: str) -> dict[str, str]:
    return {
        "X-User-Id": user_id,
        "X-User-Role": role,
    }


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


def test_evaluate_requires_auth_headers(tmp_path: Path) -> None:
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