"""
Unit tests for the dashboard summary endpoint.

GET /api/v1/dashboard/summary

Requirements: 9.1
"""

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db
from app.models.invoice import Invoice
from app.models.student import Student
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
def viewer_token(app, client):
    """Create a viewer user and return a valid JWT access token."""
    with app.app_context():
        viewer = User(
            username="dashviewer",
            email="dashviewer@example.com",
            role="viewer",
            is_active=True,
        )
        viewer.set_password("viewerpass123")
        db.session.add(viewer)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "dashviewer", "password": "viewerpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def admin_token(app, client):
    """Create an admin user and return a valid JWT access token."""
    with app.app_context():
        admin = User(
            username="dashadmin",
            email="dashadmin@example.com",
            role="admin",
            is_active=True,
        )
        admin.set_password("adminpass123")
        db.session.add(admin)
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "dashadmin", "password": "adminpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def seeded_data(app):
    """
    Populate the database with a deterministic set of students and invoices
    to verify each KPI field independently.

    Students:
      - student_active_1 (active)
      - student_active_2 (active)
      - student_inactive (inactive)

    Invoices:
      - paid_invoice       : total_amount=1000, outstanding_balance=0, status='paid'
      - paid_invoice_2     : total_amount=500,  outstanding_balance=0, status='paid'
      - unpaid_invoice     : total_amount=300,  outstanding_balance=300, status='unpaid'
      - overdue_invoice_1  : total_amount=200,  outstanding_balance=200, status='overdue'
      - overdue_invoice_2  : total_amount=150,  outstanding_balance=150, status='overdue'
      - cancelled_invoice  : total_amount=400,  outstanding_balance=400, status='cancelled'
      - forecast_invoice   : due_date=today+15, outstanding_balance=250, status='unpaid'
      - past_invoice       : due_date=today-5,  outstanding_balance=100, status='unpaid'
    """
    today = date.today()
    with app.app_context():
        # Students
        s1 = Student(
            student_number="STU-TEST-001",
            first_name="Alice",
            last_name="Smith",
            email="alice@test.com",
            enrollment_date=date(2022, 1, 1),
            status="active",
        )
        s2 = Student(
            student_number="STU-TEST-002",
            first_name="Bob",
            last_name="Jones",
            email="bob@test.com",
            enrollment_date=date(2022, 6, 1),
            status="active",
        )
        s3 = Student(
            student_number="STU-TEST-003",
            first_name="Carol",
            last_name="Lee",
            email="carol@test.com",
            enrollment_date=date(2021, 9, 1),
            status="inactive",
        )
        db.session.add_all([s1, s2, s3])
        db.session.flush()

        invoices = [
            Invoice(
                invoice_number="INV-PAID-001",
                student_id=s1.id,
                total_amount=Decimal("1000.00"),
                outstanding_balance=Decimal("0.00"),
                status="paid",
                due_date=today - timedelta(days=30),
            ),
            Invoice(
                invoice_number="INV-PAID-002",
                student_id=s2.id,
                total_amount=Decimal("500.00"),
                outstanding_balance=Decimal("0.00"),
                status="paid",
                due_date=today - timedelta(days=10),
            ),
            Invoice(
                invoice_number="INV-UNPAID-001",
                student_id=s1.id,
                total_amount=Decimal("300.00"),
                outstanding_balance=Decimal("300.00"),
                status="unpaid",
                due_date=today + timedelta(days=5),
            ),
            Invoice(
                invoice_number="INV-OVERDUE-001",
                student_id=s2.id,
                total_amount=Decimal("200.00"),
                outstanding_balance=Decimal("200.00"),
                status="overdue",
                due_date=today - timedelta(days=3),
            ),
            Invoice(
                invoice_number="INV-OVERDUE-002",
                student_id=s1.id,
                total_amount=Decimal("150.00"),
                outstanding_balance=Decimal("150.00"),
                status="overdue",
                due_date=today - timedelta(days=1),
            ),
            Invoice(
                invoice_number="INV-CANCELLED-001",
                student_id=s3.id,
                total_amount=Decimal("400.00"),
                outstanding_balance=Decimal("400.00"),
                status="cancelled",
                due_date=today - timedelta(days=60),
            ),
            # within 30-day forecast window (today+15)
            Invoice(
                invoice_number="INV-FORECAST-001",
                student_id=s1.id,
                total_amount=Decimal("250.00"),
                outstanding_balance=Decimal("250.00"),
                status="unpaid",
                due_date=today + timedelta(days=15),
            ),
            # outside 30-day window — past (today-5)
            Invoice(
                invoice_number="INV-PAST-001",
                student_id=s2.id,
                total_amount=Decimal("100.00"),
                outstanding_balance=Decimal("100.00"),
                status="unpaid",
                due_date=today - timedelta(days=5),
            ),
        ]
        db.session.add_all(invoices)
        db.session.commit()

    return {
        "expected_total_collected": "1500.00",    # 1000 + 500
        # unpaid: 300 (today+5) + 250 (today+15) + 100 (today-5) = 650
        # overdue: 200 + 150 = 350
        # total_outstanding = 650 + 350 = 1000
        "expected_total_outstanding": "1000.00",
        "expected_overdue_count": 2,
        "expected_active_student_count": 2,
        # forecast: INV-UNPAID-001 (due today+5, 300) + INV-FORECAST-001 (due today+15, 250)
        "expected_forecast_30d": "550.00",
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestDashboardAccessControl:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 401

    def test_viewer_role_returns_200(self, client, viewer_token):
        """Any authenticated user (viewer or admin) can access the summary."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 200

    def test_admin_role_returns_200(self, client, admin_token):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

class TestDashboardResponseStructure:
    def test_response_has_data_envelope(self, client, admin_token, seeded_data):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        body = resp.get_json()
        assert "data" in body

    def test_response_contains_all_required_fields(self, client, admin_token, seeded_data):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        expected_keys = {
            "total_collected",
            "total_outstanding",
            "overdue_count",
            "active_student_count",
            "forecast_30d",
        }
        assert expected_keys == set(data.keys())

    def test_decimal_amounts_are_strings(self, client, admin_token, seeded_data):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert isinstance(data["total_collected"], str)
        assert isinstance(data["total_outstanding"], str)
        assert isinstance(data["forecast_30d"], str)

    def test_counts_are_integers(self, client, admin_token, seeded_data):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert isinstance(data["overdue_count"], int)
        assert isinstance(data["active_student_count"], int)

    def test_decimal_amounts_have_two_decimal_places(self, client, admin_token, seeded_data):
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        for field in ("total_collected", "total_outstanding", "forecast_30d"):
            value = data[field]
            assert "." in value, f"{field} should contain a decimal point"
            decimal_part = value.split(".")[1]
            assert len(decimal_part) == 2, f"{field} should have exactly 2 decimal places"


# ---------------------------------------------------------------------------
# KPI value correctness
# ---------------------------------------------------------------------------

class TestDashboardKPIValues:
    def test_total_collected(self, client, admin_token, seeded_data):
        """total_collected = SUM(total_amount) for paid invoices."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["total_collected"] == seeded_data["expected_total_collected"]

    def test_total_outstanding(self, client, admin_token, seeded_data):
        """total_outstanding = SUM(outstanding_balance) for unpaid and overdue invoices."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["total_outstanding"] == seeded_data["expected_total_outstanding"]

    def test_overdue_count(self, client, admin_token, seeded_data):
        """overdue_count = COUNT of invoices with status='overdue'."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["overdue_count"] == seeded_data["expected_overdue_count"]

    def test_active_student_count(self, client, admin_token, seeded_data):
        """active_student_count = COUNT of students with status='active'."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["active_student_count"] == seeded_data["expected_active_student_count"]

    def test_forecast_30d(self, client, admin_token, seeded_data):
        """forecast_30d = SUM(outstanding_balance) for invoices due within next 30 days."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        assert data["forecast_30d"] == seeded_data["expected_forecast_30d"]

    def test_cancelled_invoices_excluded_from_outstanding(
        self, client, admin_token, seeded_data
    ):
        """Cancelled invoices should not contribute to total_outstanding."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        # unpaid: 300 + 250 + 100 = 650; overdue: 200 + 150 = 350; total = 1000
        # cancelled 400 must NOT be included (would make it 1400)
        data = resp.get_json()["data"]
        outstanding = Decimal(data["total_outstanding"])
        assert outstanding == Decimal("1000.00")

    def test_past_invoices_excluded_from_forecast(self, client, admin_token, seeded_data):
        """Invoices with due_date in the past should not appear in forecast_30d."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        # INV-PAST-001 (due today-5, balance 100) must NOT be in forecast
        # forecast = 300 (today+5) + 250 (today+15) = 550 (not 650)
        forecast = Decimal(data["forecast_30d"])
        assert forecast == Decimal("550.00")

    def test_inactive_students_excluded_from_active_count(
        self, client, admin_token, seeded_data
    ):
        """Inactive students must not be counted in active_student_count."""
        resp = client.get(
            "/api/v1/dashboard/summary",
            headers=_auth_header(admin_token),
        )
        data = resp.get_json()["data"]
        # Only s1 and s2 are active; s3 is inactive
        assert data["active_student_count"] == 2


# ---------------------------------------------------------------------------
# Empty database edge case
# ---------------------------------------------------------------------------

class TestDashboardEmptyDatabase:
    """Verify the endpoint returns zeroes when no invoices/students exist."""

    @pytest.fixture(scope="class")
    def empty_app(self):
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

    @pytest.fixture(scope="class")
    def empty_client(self, empty_app):
        return empty_app.test_client()

    @pytest.fixture(scope="class")
    def empty_token(self, empty_app, empty_client):
        with empty_app.app_context():
            user = User(
                username="emptyuser",
                email="emptyuser@example.com",
                role="admin",
                is_active=True,
            )
            user.set_password("emptypass123")
            db.session.add(user)
            db.session.commit()

        resp = empty_client.post(
            "/api/v1/auth/login",
            json={"username": "emptyuser", "password": "emptypass123"},
        )
        return resp.get_json()["data"]["access_token"]

    def test_empty_db_returns_zero_totals(self, empty_client, empty_token):
        resp = empty_client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {empty_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total_collected"] == "0.00"
        assert data["total_outstanding"] == "0.00"
        assert data["overdue_count"] == 0
        assert data["active_student_count"] == 0
        assert data["forecast_30d"] == "0.00"
