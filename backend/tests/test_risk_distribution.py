"""
Unit tests for the GET /api/v1/risk/distribution endpoint.

Requirements: 6.11, 11.5

Key invariant tested:
    low_count + medium_count + high_count == total  (Property 6 - Risk Distribution Additivity)
"""

import os
from datetime import date, datetime

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db
from app.models.risk_score import RiskScore
from app.models.student import Student
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    """Flask test app backed by an in-memory SQLite database."""
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
def viewer_token(app, client):
    """Create a viewer/staff user and return a valid JWT."""
    with app.app_context():
        user = User(
            username="riskviewer",
            email="riskviewer@example.com",
            role="viewer",
            is_active=True,
        )
        user.set_password("viewerpass123")
        db.session.add(user)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "riskviewer", "password": "viewerpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def admin_token(app, client):
    """Create an admin user and return a valid JWT."""
    with app.app_context():
        user = User(
            username="riskadmin",
            email="riskadmin@example.com",
            role="admin",
            is_active=True,
        )
        user.set_password("adminpass123")
        db.session.add(user)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "riskadmin", "password": "adminpass123"},
    )
    return resp.get_json()["data"]["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers for creating test data
# ---------------------------------------------------------------------------


def _make_student(suffix: str, status: str = "active") -> Student:
    return Student(
        student_number=f"STU-RISK-{suffix}",
        first_name=f"First{suffix}",
        last_name=f"Last{suffix}",
        email=f"student{suffix}@risk.test",
        enrollment_date=date(2023, 1, 1),
        status=status,
    )


def _make_score(student_id: int, category: str, computed_at: datetime, version: str = "v1.0.0") -> RiskScore:
    score_map = {"low": 20.0, "medium": 55.0, "high": 80.0}
    return RiskScore(
        student_id=student_id,
        score=score_map[category],
        risk_category=category,
        model_version=version,
        computed_at=computed_at,
    )


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


class TestDistributionAccessControl:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/risk/distribution")
        assert resp.status_code == 401

    def test_viewer_can_access(self, client, viewer_token):
        resp = client.get("/api/v1/risk/distribution", headers=_auth(viewer_token))
        assert resp.status_code == 200

    def test_admin_can_access(self, client, admin_token):
        resp = client.get("/api/v1/risk/distribution", headers=_auth(admin_token))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


class TestDistributionResponseStructure:
    def test_has_data_envelope(self, client, admin_token):
        resp = client.get("/api/v1/risk/distribution", headers=_auth(admin_token))
        assert "data" in resp.get_json()

    def test_data_has_required_keys(self, client, admin_token):
        data = client.get("/api/v1/risk/distribution", headers=_auth(admin_token)).get_json()["data"]
        assert set(data.keys()) == {"low_count", "medium_count", "high_count", "total"}

    def test_all_values_are_integers(self, client, admin_token):
        data = client.get("/api/v1/risk/distribution", headers=_auth(admin_token)).get_json()["data"]
        for key in ("low_count", "medium_count", "high_count", "total"):
            assert isinstance(data[key], int), f"{key} should be an integer"


# ---------------------------------------------------------------------------
# Empty database: all zeros
# ---------------------------------------------------------------------------


class TestDistributionEmptyDatabase:
    """When no active students have risk scores, all counts should be zero."""

    @pytest.fixture(scope="class")
    def empty_app(self):
        application = create_app("testing")
        application.config.update(
            {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
        )
        with application.app_context():
            db.create_all()
            yield application
            db.drop_all()

    @pytest.fixture(scope="class")
    def empty_client(self, empty_app):
        return empty_app.test_client()

    @pytest.fixture(scope="class")
    def empty_token(self, empty_app, empty_client):
        with empty_app.app_context():
            user = User(
                username="emptyrisker",
                email="emptyrisker@example.com",
                role="admin",
                is_active=True,
            )
            user.set_password("pass123")
            db.session.add(user)
            db.session.commit()
        resp = empty_client.post(
            "/api/v1/auth/login",
            json={"username": "emptyrisker", "password": "pass123"},
        )
        return resp.get_json()["data"]["access_token"]

    def test_empty_db_all_zero(self, empty_client, empty_token):
        resp = empty_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {empty_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["low_count"] == 0
        assert data["medium_count"] == 0
        assert data["high_count"] == 0
        assert data["total"] == 0

    def test_empty_db_additivity(self, empty_client, empty_token):
        """Additivity invariant: low + medium + high == total even for zeros."""
        data = empty_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {empty_token}"},
        ).get_json()["data"]
        assert data["low_count"] + data["medium_count"] + data["high_count"] == data["total"]


# ---------------------------------------------------------------------------
# Seeded data tests
# ---------------------------------------------------------------------------


class TestDistributionWithData:
    """
    Seed: 3 active students (1 low, 1 medium, 1 high) + 1 inactive student.
    Each active student has 2 RiskScore rows (old and new) to validate the
    latest-score subquery.
    An additional active student has NO score — must be excluded from counts.
    """

    @pytest.fixture(scope="class", autouse=True)
    def seed(self, app):
        with app.app_context():
            s_low = _make_student("L01", "active")
            s_med = _make_student("M01", "active")
            s_high = _make_student("H01", "active")
            s_no_score = _make_student("N01", "active")   # no score — excluded
            s_inactive = _make_student("I01", "inactive")  # inactive — excluded
            db.session.add_all([s_low, s_med, s_high, s_no_score, s_inactive])
            db.session.flush()

            t_old = datetime(2024, 1, 1, 0, 0, 0)
            t_new = datetime(2025, 1, 1, 0, 0, 0)

            # s_low: old=medium, new=low  → should count as 'low'
            db.session.add(_make_score(s_low.id, "medium", t_old))
            db.session.add(_make_score(s_low.id, "low", t_new))

            # s_med: old=high, new=medium → should count as 'medium'
            db.session.add(_make_score(s_med.id, "high", t_old))
            db.session.add(_make_score(s_med.id, "medium", t_new))

            # s_high: only one score → 'high'
            db.session.add(_make_score(s_high.id, "high", t_new))

            # s_inactive gets a score but is inactive → must be excluded
            db.session.add(_make_score(s_inactive.id, "high", t_new))

            db.session.commit()

    def _data(self, client, admin_token):
        return client.get(
            "/api/v1/risk/distribution", headers=_auth(admin_token)
        ).get_json()["data"]

    # --- Additivity invariant (Property 6) ---

    def test_additivity_invariant(self, client, admin_token):
        """
        low_count + medium_count + high_count must always equal total.

        **Validates: Requirements 6.11, 11.5**
        """
        data = self._data(client, admin_token)
        assert data["low_count"] + data["medium_count"] + data["high_count"] == data["total"]

    # --- Individual counts ---

    def test_low_count(self, client, admin_token):
        data = self._data(client, admin_token)
        assert data["low_count"] == 1

    def test_medium_count(self, client, admin_token):
        data = self._data(client, admin_token)
        assert data["medium_count"] == 1

    def test_high_count(self, client, admin_token):
        data = self._data(client, admin_token)
        assert data["high_count"] == 1

    def test_total(self, client, admin_token):
        data = self._data(client, admin_token)
        assert data["total"] == 3

    def test_inactive_student_excluded(self, client, admin_token):
        """Inactive student's score should not appear in any count."""
        data = self._data(client, admin_token)
        # Without exclusion the inactive student's 'high' would make high_count == 2
        assert data["high_count"] == 1

    def test_unscored_active_student_excluded(self, client, admin_token):
        """Active student with no score must not contribute to total."""
        data = self._data(client, admin_token)
        # There are 4 active students but only 3 have scores → total must be 3
        assert data["total"] == 3

    def test_latest_score_used(self, client, admin_token):
        """Only the most recent score per student is counted."""
        data = self._data(client, admin_token)
        # s_low's old score was 'medium' — if old scores were counted we'd have 2 medium
        assert data["medium_count"] == 1
        # s_med's old score was 'high' — if old scores were counted we'd have 3 high
        assert data["high_count"] == 1


# ---------------------------------------------------------------------------
# Missing category defaults to 0
# ---------------------------------------------------------------------------


class TestDistributionMissingCategories:
    """Verify categories with zero students still appear with count 0."""

    @pytest.fixture(scope="class")
    def single_app(self):
        application = create_app("testing")
        application.config.update(
            {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
        )
        with application.app_context():
            db.create_all()

            # Only one active student with a 'high' score
            user = User(
                username="singleadmin",
                email="singleadmin@example.com",
                role="admin",
                is_active=True,
            )
            user.set_password("pass123")
            db.session.add(user)

            s = _make_student("ONLY01", "active")
            db.session.add(s)
            db.session.flush()
            db.session.add(_make_score(s.id, "high", datetime(2025, 1, 1)))
            db.session.commit()

            yield application
            db.drop_all()

    @pytest.fixture(scope="class")
    def single_client(self, single_app):
        return single_app.test_client()

    @pytest.fixture(scope="class")
    def single_token(self, single_app, single_client):
        resp = single_client.post(
            "/api/v1/auth/login",
            json={"username": "singleadmin", "password": "pass123"},
        )
        return resp.get_json()["data"]["access_token"]

    def test_missing_low_defaults_to_zero(self, single_client, single_token):
        data = single_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {single_token}"},
        ).get_json()["data"]
        assert data["low_count"] == 0

    def test_missing_medium_defaults_to_zero(self, single_client, single_token):
        data = single_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {single_token}"},
        ).get_json()["data"]
        assert data["medium_count"] == 0

    def test_high_count_and_total_correct(self, single_client, single_token):
        data = single_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {single_token}"},
        ).get_json()["data"]
        assert data["high_count"] == 1
        assert data["total"] == 1

    def test_additivity_with_missing_categories(self, single_client, single_token):
        """Additivity must hold even when some categories are absent."""
        data = single_client.get(
            "/api/v1/risk/distribution",
            headers={"Authorization": f"Bearer {single_token}"},
        ).get_json()["data"]
        assert data["low_count"] + data["medium_count"] + data["high_count"] == data["total"]
