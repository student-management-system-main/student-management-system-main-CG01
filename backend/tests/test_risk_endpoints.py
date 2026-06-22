"""
Unit tests for the Risk API proxy endpoints:
    POST /api/v1/risk/score
    POST /api/v1/risk/retrain

Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Set env vars before any app import
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    """Flask test application with an in-memory SQLite database."""
    application = create_app("testing")
    application.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "RISK_SERVICE_URL": "http://mock-risk-service:5001",
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
        user = User(
            username="riskendpointadmin",
            email="riskendpointadmin@example.com",
            role="admin",
            is_active=True,
        )
        user.set_password("adminpass456")
        db.session.add(user)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "riskendpointadmin", "password": "adminpass456"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def staff_token(app, client):
    """Create a viewer (non-admin) user and return a valid JWT access token.

    The User model's role enum only supports 'admin' and 'viewer'.
    We use 'viewer' here to represent a non-admin user (analogous to 'staff').
    The @admin_required decorator rejects all non-admin roles with 403.
    """
    with app.app_context():
        user = User(
            username="riskendpointstaff",
            email="riskendpointstaff@example.com",
            role="viewer",
            is_active=True,
        )
        user.set_password("staffpass456")
        db.session.add(user)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "riskendpointstaff", "password": "staffpass456"},
    )
    return resp.get_json()["data"]["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _mock_requests_post(status_code: int, json_body: dict) -> MagicMock:
    """Build a mock requests.Response returned by requests.post."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_body
    return mock_resp


# ---------------------------------------------------------------------------
# POST /api/v1/risk/score
# ---------------------------------------------------------------------------


class TestScoreEndpointAuth:
    """Access-control tests for POST /api/v1/risk/score."""

    def test_unauthenticated_returns_401(self, client):
        """No token → 401."""
        resp = client.post("/api/v1/risk/score", json={"student_id": 1})
        assert resp.status_code == 401

    def test_staff_role_returns_403(self, client, staff_token):
        """Viewer (non-admin) role → 403 FORBIDDEN."""
        resp = client.post(
            "/api/v1/risk/score",
            json={"student_id": 1},
            headers=_auth(staff_token),
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"]["code"] == "FORBIDDEN"


class TestScoreEndpointValidation:
    """Input-validation tests for POST /api/v1/risk/score."""

    def test_missing_student_id_returns_400(self, client, admin_token):
        """Missing student_id field → 400 VALIDATION_ERROR."""
        resp = client.post(
            "/api/v1/risk/score",
            json={},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_non_integer_student_id_string_returns_400(self, client, admin_token):
        """String student_id → 400 VALIDATION_ERROR."""
        resp = client.post(
            "/api/v1/risk/score",
            json={"student_id": "abc"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_non_integer_student_id_float_returns_400(self, client, admin_token):
        """Float student_id → 400 VALIDATION_ERROR (must be integer)."""
        resp = client.post(
            "/api/v1/risk/score",
            json={"student_id": 1.5},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_null_student_id_returns_400(self, client, admin_token):
        """Null student_id → 400 VALIDATION_ERROR."""
        resp = client.post(
            "/api/v1/risk/score",
            json={"student_id": None},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_no_json_body_returns_400(self, client, admin_token):
        """No JSON body → treated as empty → 400 VALIDATION_ERROR."""
        resp = client.post(
            "/api/v1/risk/score",
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"


class TestScoreEndpointSuccess:
    """Successful proxy tests for POST /api/v1/risk/score."""

    def test_successful_score_returns_200_with_risk_service_payload(
        self, client, admin_token
    ):
        """Admin with valid student_id → 200 with Risk Service JSON response."""
        risk_payload = {
            "student_id": 42,
            "score": 75.5,
            "risk_category": "high",
            "model_version": "v1.0.0",
            "computed_at": "2025-01-01T00:00:00Z",
        }

        with patch("requests.post", return_value=_mock_requests_post(200, risk_payload)):
            resp = client.post(
                "/api/v1/risk/score",
                json={"student_id": 42},
                headers=_auth(admin_token),
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["student_id"] == 42
        assert body["score"] == 75.5
        assert body["risk_category"] == "high"

    def test_risk_service_400_is_passed_through(self, client, admin_token):
        """Risk Service 400 (inactive student) → proxied as 400."""
        error_payload = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Student is inactive.",
                "details": {},
            }
        }

        with patch("requests.post", return_value=_mock_requests_post(400, error_payload)):
            resp = client.post(
                "/api/v1/risk/score",
                json={"student_id": 99},
                headers=_auth(admin_token),
            )

        assert resp.status_code == 400

    def test_risk_service_404_is_passed_through(self, client, admin_token):
        """Risk Service 404 (student not found) → proxied as 404."""
        error_payload = {
            "error": {
                "code": "NOT_FOUND",
                "message": "Student not found.",
                "details": {},
            }
        }

        with patch("requests.post", return_value=_mock_requests_post(404, error_payload)):
            resp = client.post(
                "/api/v1/risk/score",
                json={"student_id": 9999},
                headers=_auth(admin_token),
            )

        assert resp.status_code == 404


class TestScoreEndpointServiceUnavailable:
    """Unreachable Risk Service tests for POST /api/v1/risk/score."""

    def test_connection_error_returns_503(self, client, admin_token):
        """ConnectionError from Risk Service → 503 SERVICE_UNAVAILABLE."""
        import requests as req_module

        with patch("requests.post", side_effect=req_module.ConnectionError("refused")):
            resp = client.post(
                "/api/v1/risk/score",
                json={"student_id": 1},
                headers=_auth(admin_token),
            )

        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_timeout_returns_503(self, client, admin_token):
        """Timeout from Risk Service → 503 SERVICE_UNAVAILABLE."""
        import requests as req_module

        with patch("requests.post", side_effect=req_module.Timeout("timed out")):
            resp = client.post(
                "/api/v1/risk/score",
                json={"student_id": 1},
                headers=_auth(admin_token),
            )

        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# POST /api/v1/risk/retrain
# ---------------------------------------------------------------------------


class TestRetrainEndpointAuth:
    """Access-control tests for POST /api/v1/risk/retrain."""

    def test_unauthenticated_returns_401(self, client):
        """No token → 401."""
        resp = client.post("/api/v1/risk/retrain")
        assert resp.status_code == 401

    def test_staff_role_returns_403(self, client, staff_token):
        """Viewer (non-admin) role → 403 FORBIDDEN."""
        resp = client.post(
            "/api/v1/risk/retrain",
            headers=_auth(staff_token),
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"]["code"] == "FORBIDDEN"


class TestRetrainEndpointSuccess:
    """Successful proxy tests for POST /api/v1/risk/retrain."""

    def test_successful_retrain_returns_200_with_risk_service_payload(
        self, client, admin_token
    ):
        """Admin calling retrain → 200 with Risk Service JSON response."""
        risk_payload = {
            "new_roc_auc": 0.87,
            "current_roc_auc": 0.82,
            "replaced": True,
            "version": "v1.0.1",
            "n_samples": 50,
        }

        with patch("requests.post", return_value=_mock_requests_post(200, risk_payload)):
            resp = client.post(
                "/api/v1/risk/retrain",
                headers=_auth(admin_token),
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["replaced"] is True
        assert body["version"] == "v1.0.1"
        assert body["new_roc_auc"] == 0.87

    def test_retrain_not_replaced_returns_200(self, client, admin_token):
        """Retrain where new model did not beat current → 200 with replaced=False."""
        risk_payload = {
            "new_roc_auc": 0.75,
            "current_roc_auc": 0.82,
            "replaced": False,
            "version": "v1.0.0",
            "n_samples": 50,
        }

        with patch("requests.post", return_value=_mock_requests_post(200, risk_payload)):
            resp = client.post(
                "/api/v1/risk/retrain",
                headers=_auth(admin_token),
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["replaced"] is False


class TestRetrainEndpointServiceUnavailable:
    """Unreachable Risk Service tests for POST /api/v1/risk/retrain."""

    def test_connection_error_returns_503(self, client, admin_token):
        """ConnectionError from Risk Service → 503 SERVICE_UNAVAILABLE."""
        import requests as req_module

        with patch("requests.post", side_effect=req_module.ConnectionError("refused")):
            resp = client.post(
                "/api/v1/risk/retrain",
                headers=_auth(admin_token),
            )

        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_timeout_returns_503(self, client, admin_token):
        """Timeout from Risk Service → 503 SERVICE_UNAVAILABLE."""
        import requests as req_module

        with patch("requests.post", side_effect=req_module.Timeout("timed out")):
            resp = client.post(
                "/api/v1/risk/retrain",
                headers=_auth(admin_token),
            )

        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
