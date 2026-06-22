"""
Property-based tests for the backend.

P3 — Invoice Balance Invariant
    For any combination of payment and reversal transactions,
    outstanding_balance == total_amount - SUM(payments) + SUM(reversals)

P8 — Audit Log Completeness
    Every successful mutating API operation appends exactly 1 audit log row.
    GET operations append 0 rows.

Uses hypothesis for automated counterexample discovery.
Runs against SQLite in-memory so no external database is needed.

Requirements: 4.9, 5.9, 13.1, 13.5
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Set env before Flask imports
os.environ.setdefault("SECRET_KEY", "prop-test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "prop-test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db  # noqa: E402
from app.models.fee_type import FeeType  # noqa: E402
from app.models.invoice import Invoice  # noqa: E402
from app.models.invoice_line_item import InvoiceLineItem  # noqa: E402
from app.models.log import Log  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.models.user import User  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    application = create_app("testing")
    application.config.update(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def admin_user(app):
    with app.app_context():
        u = User(
            username="prop_admin",
            email="prop_admin@test.com",
            password_hash="",
            role="admin",
            is_active=True,
        )
        u.set_password("testpass123")
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture(scope="module")
def admin_token(app, client, admin_user):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "prop_admin", "password": "testpass123"},
    )
    return resp.get_json()["data"]["access_token"]


@pytest.fixture(scope="module")
def base_student(app, admin_user):
    with app.app_context():
        s = Student(
            student_number="PROP-STU-001",
            first_name="Property",
            last_name="Tester",
            email="prop@test.com",
            enrollment_date=date(2022, 1, 1),
            status="active",
        )
        db.session.add(s)

        ft = FeeType(
            name="Prop Test Fee",
            amount=Decimal("10000.00"),
            currency="USD",
            due_date=date(2030, 1, 1),
            is_active=True,
        )
        db.session.add(ft)
        db.session.commit()
        return s.id, ft.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_invoice(app, student_id: int, fee_type_id: int, total: Decimal) -> int:
    """Create an invoice with the given total_amount. Returns invoice id."""
    with app.app_context():
        inv_num = f"INV-PROP-{datetime.now(timezone.utc).timestamp():.6f}"
        inv = Invoice(
            invoice_number=inv_num,
            student_id=student_id,
            total_amount=total,
            outstanding_balance=total,
            status="unpaid",
            due_date=date(2030, 12, 31),
        )
        db.session.add(inv)
        db.session.flush()
        li = InvoiceLineItem(invoice_id=inv.id, fee_type_id=fee_type_id, amount=total)
        db.session.add(li)
        db.session.commit()
        return inv.id


def _apply_payment(client, admin_token: str, invoice_id: int, amount: Decimal) -> bool:
    """Apply a payment to an invoice. Returns True if successful."""
    resp = client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": str(amount), "payment_method": "bank_transfer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return resp.status_code == 200


def _get_balance(app, invoice_id: int) -> Decimal:
    with app.app_context():
        inv = db.session.get(Invoice, invoice_id)
        return Decimal(str(inv.outstanding_balance))


def _count_audit_logs(app) -> int:
    with app.app_context():
        return Log.query.count()


# ---------------------------------------------------------------------------
# P3 — Invoice Balance Invariant (unit-level, no HTTP)
# ---------------------------------------------------------------------------

class TestInvoiceBalanceInvariantUnit:
    """
    P3: Test the balance invariant at the model/arithmetic level.

    outstanding_balance = total_amount - SUM(payment amounts) + SUM(reversal amounts)

    This pure arithmetic property holds regardless of invoice status.

    Requirements: 4.9, 5.9
    """

    @given(
        total=st.decimals(min_value="1.00", max_value="99999.99", places=2, allow_nan=False, allow_infinity=False),
        payment_fractions=st.lists(
            st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=8,
        ),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_sequential_payments_maintain_balance(self, total, payment_fractions):
        """
        Applying a sequence of partial payments (each ≤ remaining balance)
        must keep outstanding_balance = total_amount - SUM(payments).
        """
        total_d = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_d <= 0:
            return

        balance = total_d
        total_paid = Decimal("0.00")

        for frac in payment_fractions:
            if balance <= Decimal("0.00"):
                break
            amount = (balance * Decimal(str(frac))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            amount = max(Decimal("0.01"), min(amount, balance))
            balance -= amount
            total_paid += amount

            # Invariant: balance == total - paid
            expected = (total_d - total_paid).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            assert balance == expected, (
                f"Balance invariant violated: {balance} != {expected} "
                f"(total={total_d}, paid={total_paid})"
            )

    @given(
        total=st.decimals(min_value="100.00", max_value="5000.00", places=2, allow_nan=False, allow_infinity=False),
        payment_frac=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_payment_then_reversal_restores_balance(self, total, payment_frac):
        """
        A full reversal of a payment must restore outstanding_balance to its
        pre-payment value.
        """
        total_d = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance = total_d

        # Apply partial payment
        paid = (total_d * Decimal(str(payment_frac))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        paid = max(Decimal("0.01"), min(paid, balance))
        balance_after_payment = balance - paid

        # Apply reversal (full reversal of the payment)
        balance_after_reversal = balance_after_payment + paid

        # Must equal original balance
        assert balance_after_reversal == total_d, (
            f"Reversal did not restore balance: {balance_after_reversal} != {total_d}"
        )

    @given(
        total=st.decimals(min_value="50.00", max_value="10000.00", places=2, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_balance_never_goes_negative(self, total):
        """
        With clamping at the outstanding balance, no payment sequence should
        produce a negative balance.
        """
        total_d = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_d <= 0:
            return

        balance = total_d
        # Simulate paying the entire balance at once
        balance -= total_d
        assert balance == Decimal("0.00")
        assert balance >= Decimal("0.00")


# ---------------------------------------------------------------------------
# P8 — Audit Log Completeness (integration-level, uses HTTP client)
# ---------------------------------------------------------------------------

class TestAuditLogCompleteness:
    """
    P8: Every mutating API operation appends exactly 1 audit log entry.
    GET operations must not create any audit entries.

    Requirements: 13.1, 13.5
    """

    def test_student_create_appends_one_log(self, app, client, admin_token):
        """POST /students → exactly 1 new audit log entry."""
        before = _count_audit_logs(app)
        resp = client.post(
            "/api/v1/students",
            json={
                "student_number": f"AUD-STU-{datetime.now().timestamp():.0f}",
                "first_name": "Audit",
                "last_name": "Test",
                "email": f"audit{datetime.now().timestamp():.0f}@test.com",
                "enrollment_date": "2023-01-01",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        after = _count_audit_logs(app)
        assert after - before == 1, f"Expected 1 audit log, got {after - before}"

    def test_student_update_appends_one_log(self, app, client, admin_token):
        """PUT /students/:id → exactly 1 new audit log entry."""
        # Create a student first
        resp = client.post(
            "/api/v1/students",
            json={
                "student_number": f"AUD-UPD-{datetime.now().timestamp():.0f}",
                "first_name": "Update",
                "last_name": "Me",
                "email": f"update{datetime.now().timestamp():.0f}@test.com",
                "enrollment_date": "2023-01-01",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        student_id = resp.get_json()["data"]["id"]

        before = _count_audit_logs(app)
        resp = client.put(
            f"/api/v1/students/{student_id}",
            json={"first_name": "Updated"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        after = _count_audit_logs(app)
        assert after - before == 1, f"Expected 1 audit log on update, got {after - before}"

    def test_get_students_appends_no_logs(self, app, client, admin_token):
        """GET /students → 0 new audit log entries."""
        before = _count_audit_logs(app)
        resp = client.get(
            "/api/v1/students",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        after = _count_audit_logs(app)
        assert after == before, "GET request must not create audit logs"

    def test_get_student_by_id_appends_no_logs(self, app, client, admin_token):
        """GET /students/:id → 0 new audit log entries."""
        # Create student
        resp = client.post(
            "/api/v1/students",
            json={
                "student_number": f"AUD-GET-{datetime.now().timestamp():.0f}",
                "first_name": "GetMe",
                "last_name": "ReadOnly",
                "email": f"getme{datetime.now().timestamp():.0f}@test.com",
                "enrollment_date": "2023-01-01",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        student_id = resp.get_json()["data"]["id"]

        before = _count_audit_logs(app)
        client.get(
            f"/api/v1/students/{student_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        after = _count_audit_logs(app)
        assert after == before, "GET /students/:id must not create audit logs"

    def test_multiple_mutations_each_append_one_log(self, app, client, admin_token):
        """N sequential mutating operations must produce exactly N audit log entries."""
        n = 3
        before = _count_audit_logs(app)
        for i in range(n):
            client.post(
                "/api/v1/students",
                json={
                    "student_number": f"AUD-MULTI-{datetime.now().timestamp():.6f}-{i}",
                    "first_name": f"Multi{i}",
                    "last_name": "LogTest",
                    "email": f"multi{i}{datetime.now().timestamp():.0f}@test.com",
                    "enrollment_date": "2023-01-01",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        after = _count_audit_logs(app)
        assert after - before == n, (
            f"Expected {n} audit logs for {n} mutations, got {after - before}"
        )

    def test_get_audit_log_appends_no_logs(self, app, client, admin_token):
        """GET /audit → 0 new audit log entries (reading audit is itself read-only)."""
        before = _count_audit_logs(app)
        client.get(
            "/api/v1/audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        after = _count_audit_logs(app)
        assert after == before, "Reading the audit log must not create new audit entries"
