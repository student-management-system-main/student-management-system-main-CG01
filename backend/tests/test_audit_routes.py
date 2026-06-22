"""
Unit tests for the audit log query endpoint.

GET /api/v1/audit — Admin only; filterable, paginated audit log query

Requirements: 9.1, 9.3, 9.4
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db
from app.models.log import Log
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    """Create a Flask test application backed by an in-memory SQLite database."""
    application = create_app("testing")
    application.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def admin_token(app, client):
    """Create an admin user and return a valid JWT access token."""
    with app.app_context():
        admin = User(
            username="auditadmin",
            email="auditadmin@example.com",
            role="admin",
            is_active=True,
        )
        admin.set_password("adminpass123")
        db.session.add(admin)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "auditadmin", "password": "adminpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def viewer_token(app, client):
    """Create a viewer user and return a valid JWT access token."""
    with app.app_context():
        viewer = User(
            username="auditviewer",
            email="auditviewer@example.com",
            role="viewer",
            is_active=True,
        )
        viewer.set_password("viewerpass123")
        db.session.add(viewer)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "auditviewer", "password": "viewerpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def seed_logs(app):
    """Insert a set of Log rows to test filtering and pagination."""
    with app.app_context():
        logs = [
            Log(actor_id=1, resource_type="student", resource_id=10,
                action="create", previous_values=None, new_values={"name": "Alice"}),
            Log(actor_id=1, resource_type="student", resource_id=11,
                action="update", previous_values={"name": "Bob"},
                new_values={"name": "Bobby"}),
            Log(actor_id=2, resource_type="invoice", resource_id=5,
                action="create", previous_values=None, new_values={"amount": "500"}),
            Log(actor_id=2, resource_type="invoice", resource_id=5,
                action="update", previous_values={"status": "unpaid"},
                new_values={"status": "paid"}),
            Log(actor_id=None, resource_type="report", resource_id=None,
                action="export", previous_values=None, new_values=None),
        ]
        for log in logs:
            db.session.add(log)
        db.session.commit()
    return logs


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestAuditAccessControl:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/audit/")
        assert resp.status_code == 401

    def test_viewer_role_returns_403(self, client, viewer_token):
        resp = client.get("/api/v1/audit/", headers=_auth_header(viewer_token))
        assert resp.status_code == 403

    def test_admin_role_returns_200(self, client, admin_token, seed_logs):
        resp = client.get("/api/v1/audit/", headers=_auth_header(admin_token))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

class TestAuditResponseStructure:
    def test_response_has_data_envelope(self, client, admin_token, seed_logs):
        resp = client.get("/api/v1/audit/", headers=_auth_header(admin_token))
        body = resp.get_json()
        assert "data" in body
        data = body["data"]
        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    def test_log_entry_fields(self, client, admin_token, seed_logs):
        resp = client.get("/api/v1/audit/", headers=_auth_header(admin_token))
        logs = resp.get_json()["data"]["logs"]
        assert len(logs) > 0
        entry = logs[0]
        expected_fields = {
            "id", "actor_id", "resource_type", "resource_id", "action",
            "previous_values", "new_values", "channel", "delivery_status",
            "created_at",
        }
        assert expected_fields == set(entry.keys())

    def test_created_at_is_iso_string(self, client, admin_token, seed_logs):
        resp = client.get("/api/v1/audit/", headers=_auth_header(admin_token))
        logs = resp.get_json()["data"]["logs"]
        for entry in logs:
            if entry["created_at"] is not None:
                # Should not raise
                from datetime import datetime
                datetime.fromisoformat(entry["created_at"].replace("Z", "+00:00"))

    def test_default_page_and_per_page(self, client, admin_token, seed_logs):
        resp = client.get("/api/v1/audit/", headers=_auth_header(admin_token))
        data = resp.get_json()["data"]
        assert data["page"] == 1
        assert data["per_page"] == 50


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestAuditFiltering:
    def test_filter_by_actor_id(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?actor_id=1",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert all(log["actor_id"] == 1 for log in data["logs"])

    def test_filter_by_resource_type(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?resource_type=invoice",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert len(data["logs"]) >= 2
        assert all(log["resource_type"] == "invoice" for log in data["logs"])

    def test_filter_by_action(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?action=create",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert len(data["logs"]) >= 2
        assert all(log["action"] == "create" for log in data["logs"])

    def test_filter_by_date_from(self, client, admin_token, seed_logs):
        # date far in the future returns no results
        resp = client.get(
            "/api/v1/audit/?date_from=2999-01-01",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["logs"] == []

    def test_filter_by_date_to(self, client, admin_token, seed_logs):
        # date far in the past returns no results
        resp = client.get(
            "/api/v1/audit/?date_to=1970-01-01",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["logs"] == []

    def test_combined_filters(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?resource_type=student&action=create",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        for log in data["logs"]:
            assert log["resource_type"] == "student"
            assert log["action"] == "create"

    def test_invalid_actor_id_returns_400(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit/?actor_id=notanint",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "BAD_REQUEST"

    def test_invalid_date_from_returns_400(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit/?date_from=not-a-date",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "BAD_REQUEST"

    def test_invalid_date_to_returns_400(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit/?date_to=31/12/2024",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestAuditPagination:
    def test_per_page_respected(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?per_page=2",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert len(data["logs"]) <= 2
        assert data["per_page"] == 2

    def test_per_page_capped_at_200(self, client, admin_token, seed_logs):
        resp = client.get(
            "/api/v1/audit/?per_page=500",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["per_page"] == 200

    def test_page_2_returns_different_results(self, client, admin_token, seed_logs):
        resp_p1 = client.get(
            "/api/v1/audit/?page=1&per_page=2",
            headers=_auth_header(admin_token),
        )
        resp_p2 = client.get(
            "/api/v1/audit/?page=2&per_page=2",
            headers=_auth_header(admin_token),
        )
        ids_p1 = {log["id"] for log in resp_p1.get_json()["data"]["logs"]}
        ids_p2 = {log["id"] for log in resp_p2.get_json()["data"]["logs"]}
        # Pages should not overlap (unless total <= per_page)
        total = resp_p1.get_json()["data"]["total"]
        if total > 2:
            assert ids_p1.isdisjoint(ids_p2)

    def test_invalid_page_returns_400(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit/?page=0",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 400

    def test_invalid_per_page_returns_400(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit/?per_page=-1",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 400

    def test_total_reflects_all_matching_records(self, client, admin_token, seed_logs):
        """total should count all matching records, not just the current page."""
        resp_all = client.get(
            "/api/v1/audit/",
            headers=_auth_header(admin_token),
        )
        total_all = resp_all.get_json()["data"]["total"]

        resp_p1 = client.get(
            "/api/v1/audit/?per_page=2",
            headers=_auth_header(admin_token),
        )
        # total should be the same regardless of per_page
        assert resp_p1.get_json()["data"]["total"] == total_all


# ---------------------------------------------------------------------------
# Append-only enforcement (Requirement 9.4)
# ---------------------------------------------------------------------------

class TestAuditAppendOnly:
    def test_put_returns_405(self, client, admin_token):
        resp = client.put("/api/v1/audit/", headers=_auth_header(admin_token))
        assert resp.status_code == 405

    def test_patch_returns_405(self, client, admin_token):
        resp = client.patch("/api/v1/audit/", headers=_auth_header(admin_token))
        assert resp.status_code == 405

    def test_delete_returns_405(self, client, admin_token):
        resp = client.delete("/api/v1/audit/", headers=_auth_header(admin_token))
        assert resp.status_code == 405

    def test_put_on_subpath_returns_405(self, client, admin_token):
        resp = client.put("/api/v1/audit/1", headers=_auth_header(admin_token))
        assert resp.status_code == 405

    def test_delete_on_subpath_returns_405(self, client, admin_token):
        resp = client.delete("/api/v1/audit/1", headers=_auth_header(admin_token))
        assert resp.status_code == 405

    def test_405_response_has_error_envelope(self, client, admin_token):
        resp = client.delete("/api/v1/audit/", headers=_auth_header(admin_token))
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
