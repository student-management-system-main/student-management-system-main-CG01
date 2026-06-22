"""
Unit tests for auth endpoints: login, refresh, logout.

Requirements: 8.1, 8.4, 8.5
"""

import os
import pytest
from unittest.mock import MagicMock, patch

# Set required env vars before any app import so ProductionConfig class body
# doesn't raise KeyError when the module is first imported.
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
    """Create a Flask test application with an in-memory SQLite database."""
    application = create_app("testing")
    application.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            # Disable blocklist check by default (Redis not available in tests)
            "JWT_ACCESS_TOKEN_EXPIRES": 300,
            "JWT_REFRESH_TOKEN_EXPIRES": 600,
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
def active_user(app):
    """Create and persist an active user for login tests."""
    with app.app_context():
        user = User(
            username="testadmin",
            email="testadmin@example.com",
            role="admin",
            is_active=True,
        )
        user.set_password("correct_password")
        db.session.add(user)
        db.session.commit()
        # Detach from session so it can be used across requests
        db.session.expunge(user)
        return user


@pytest.fixture(scope="module")
def inactive_user(app):
    """Create and persist an inactive user."""
    with app.app_context():
        user = User(
            username="inactiveuser",
            email="inactive@example.com",
            role="viewer",
            is_active=False,
        )
        user.set_password("some_password")
        db.session.add(user)
        db.session.commit()
        db.session.expunge(user)
        return user


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _login(client, username="testadmin", password="correct_password"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success_returns_200_with_tokens(self, client, active_user):
        """Valid credentials return 200 with access_token, refresh_token, and user."""
        resp = _login(client)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "testadmin"
        assert "password_hash" not in data["user"]

    def test_login_missing_username_returns_400(self, client):
        """Missing username field returns 400 VALIDATION_ERROR."""
        resp = client.post("/api/v1/auth/login", json={"password": "pw"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "username" in body["error"]["details"]["missing_fields"]

    def test_login_missing_password_returns_400(self, client):
        """Missing password field returns 400 VALIDATION_ERROR."""
        resp = client.post("/api/v1/auth/login", json={"username": "testadmin"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "password" in body["error"]["details"]["missing_fields"]

    def test_login_missing_both_fields_returns_400(self, client):
        """Empty body returns 400 VALIDATION_ERROR listing both fields."""
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        missing = body["error"]["details"]["missing_fields"]
        assert "username" in missing
        assert "password" in missing

    def test_login_wrong_password_returns_401(self, client, active_user):
        """Wrong password returns 401 INVALID_CREDENTIALS."""
        resp = _login(client, password="wrong_password")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_unknown_username_returns_401(self, client):
        """Non-existent username returns 401 INVALID_CREDENTIALS (no enumeration)."""
        resp = _login(client, username="nobody", password="anything")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_wrong_and_unknown_same_message(self, client, active_user):
        """Wrong password and unknown user return the same error message (no enumeration)."""
        resp_wrong_pw = _login(client, password="wrong")
        resp_unknown = _login(client, username="nobody", password="pw")
        assert resp_wrong_pw.get_json()["error"]["message"] == \
               resp_unknown.get_json()["error"]["message"]

    def test_login_inactive_user_returns_403(self, client, inactive_user):
        """Inactive account returns 403 ACCOUNT_INACTIVE."""
        resp = _login(client, username="inactiveuser", password="some_password")
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"]["code"] == "ACCOUNT_INACTIVE"

    def test_login_no_json_body_returns_400(self, client):
        """Request with no JSON body returns 400 VALIDATION_ERROR."""
        resp = client.post("/api/v1/auth/login", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_refresh_returns_new_access_token(self, client, active_user):
        """Valid refresh token returns 200 with a new access_token."""
        login_resp = _login(client)
        refresh_token = login_resp.get_json()["data"]["refresh_token"]

        resp = client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "access_token" in data

    def test_refresh_with_access_token_returns_401(self, client, active_user):
        """Using an access token on the refresh endpoint is rejected (not a refresh token)."""
        login_resp = _login(client)
        access_token = login_resp.get_json()["data"]["access_token"]

        resp = client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # Flask-JWT-Extended rejects non-refresh tokens with 401
        assert resp.status_code in (401, 422)

    def test_refresh_without_token_returns_401(self, client):
        """Missing Authorization header returns 401."""
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_200_with_message(self, client, active_user):
        """Valid access token logout returns 200 with success message."""
        login_resp = _login(client)
        access_token = login_resp.get_json()["data"]["access_token"]

        with patch("app.auth.routes._get_redis_client") as mock_redis_factory:
            mock_redis = MagicMock()
            mock_redis_factory.return_value = mock_redis

            resp = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["message"] == "Successfully logged out"

    def test_logout_stores_jti_in_redis(self, client, active_user):
        """Logout stores the token JTI in Redis with a TTL."""
        login_resp = _login(client)
        access_token = login_resp.get_json()["data"]["access_token"]

        with patch("app.auth.routes._get_redis_client") as mock_redis_factory:
            mock_redis = MagicMock()
            mock_redis_factory.return_value = mock_redis

            client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            # setex should have been called with a blocklist key and TTL
            assert mock_redis.setex.called
            call_args = mock_redis.setex.call_args
            key = call_args[0][0]
            assert key.startswith("blocklist:")

    def test_logout_without_token_returns_401(self, client):
        """Missing Authorization header returns 401."""
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 401

    def test_logout_redis_failure_still_returns_200(self, client, active_user):
        """If Redis is unavailable, logout still returns 200 (best-effort revocation)."""
        login_resp = _login(client)
        access_token = login_resp.get_json()["data"]["access_token"]

        with patch("app.auth.routes._get_redis_client") as mock_redis_factory:
            mock_redis = MagicMock()
            mock_redis.setex.side_effect = Exception("Redis connection refused")
            mock_redis_factory.return_value = mock_redis

            resp = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        assert resp.status_code == 200
