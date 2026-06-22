"""
risk_service/tests/test_features.py
-------------------------------------
Unit tests for the feature extraction module (risk_service/features.py).

Uses an in-memory SQLite database to exercise the SQL queries without
requiring a live MySQL instance.

Requirements: 4.3
"""

from __future__ import annotations

import datetime

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from features import (
    FEATURE_NAMES,
    NUM_FEATURES,
    extract_features,
    _payment_history_ratio,
    _overdue_invoice_count,
    _total_outstanding_balance,
    _enrollment_duration_days,
    _historical_default_rate,
    _avg_days_to_pay,
    _partial_payment_count,
)


# ---------------------------------------------------------------------------
# Fixtures – in-memory SQLite database
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY,
    student_number  TEXT    NOT NULL,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    enrollment_date DATE    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS invoices (
    id                  INTEGER PRIMARY KEY,
    invoice_number      TEXT    NOT NULL,
    student_id          INTEGER NOT NULL REFERENCES students(id),
    total_amount        REAL    NOT NULL,
    outstanding_balance REAL    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'unpaid',
    due_date            DATE    NOT NULL,
    paid_at             DATETIME,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY,
    transaction_ref TEXT    NOT NULL,
    student_id      INTEGER NOT NULL REFERENCES students(id),
    invoice_id      INTEGER NOT NULL REFERENCES invoices(id),
    amount          REAL    NOT NULL,
    payment_method  TEXT    NOT NULL DEFAULT 'cash',
    type            TEXT    NOT NULL DEFAULT 'payment',
    reversal_of     INTEGER,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture()
def engine():
    """Create a fresh in-memory SQLite engine for each test."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    with eng.connect() as conn:
        for stmt in DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    return eng


@pytest.fixture()
def conn(engine):
    """Yield a SQLAlchemy Connection with an open transaction."""
    with engine.connect() as connection:
        yield connection


def _insert_student(conn, student_id: int, enrollment_date: str, status: str = "active") -> None:
    conn.execute(
        text(
            "INSERT INTO students (id, student_number, first_name, last_name, email, enrollment_date, status) "
            "VALUES (:id, :num, :fn, :ln, :email, :enroll, :status)"
        ),
        {
            "id": student_id,
            "num": f"S{student_id:04d}",
            "fn": "Test",
            "ln": "Student",
            "email": f"student{student_id}@test.com",
            "enroll": enrollment_date,
            "status": status,
        },
    )


def _insert_invoice(
    conn,
    invoice_id: int,
    student_id: int,
    total: float,
    balance: float,
    status: str,
    due_date: str,
    paid_at: str | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO invoices (id, invoice_number, student_id, total_amount, outstanding_balance, "
            "status, due_date, paid_at) "
            "VALUES (:id, :num, :sid, :total, :balance, :status, :due, :paid)"
        ),
        {
            "id": invoice_id,
            "num": f"INV-{invoice_id:04d}",
            "sid": student_id,
            "total": total,
            "balance": balance,
            "status": status,
            "due": due_date,
            "paid": paid_at,
        },
    )


def _insert_transaction(
    conn,
    txn_id: int,
    student_id: int,
    invoice_id: int,
    amount: float,
    txn_type: str = "payment",
) -> None:
    conn.execute(
        text(
            "INSERT INTO transactions (id, transaction_ref, student_id, invoice_id, amount, type) "
            "VALUES (:id, :ref, :sid, :iid, :amount, :type)"
        ),
        {
            "id": txn_id,
            "ref": f"TXN-{txn_id:04d}",
            "sid": student_id,
            "iid": invoice_id,
            "amount": amount,
            "type": txn_type,
        },
    )


# ---------------------------------------------------------------------------
# FEATURE_NAMES and NUM_FEATURES constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_feature_names_length(self):
        assert len(FEATURE_NAMES) == 7

    def test_feature_names_order(self):
        assert FEATURE_NAMES == [
            "payment_history_ratio",
            "overdue_invoice_count",
            "total_outstanding_balance",
            "enrollment_duration_days",
            "historical_default_rate",
            "avg_days_to_pay",
            "partial_payment_count",
        ]

    def test_num_features(self):
        assert NUM_FEATURES == 7


# ---------------------------------------------------------------------------
# extract_features – return type and shape
# ---------------------------------------------------------------------------

class TestExtractFeaturesShape:
    def test_returns_numpy_array(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        result = extract_features(1, conn)
        assert isinstance(result, np.ndarray)

    def test_shape_is_7(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        result = extract_features(1, conn)
        assert result.shape == (7,)

    def test_dtype_is_float64(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        result = extract_features(1, conn)
        assert result.dtype == np.float64

    def test_no_nan_values(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        result = extract_features(1, conn)
        assert not np.any(np.isnan(result))

    def test_no_inf_values(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        result = extract_features(1, conn)
        assert not np.any(np.isinf(result))

    def test_invalid_student_raises_value_error(self, conn):
        with pytest.raises(ValueError, match="does not exist"):
            extract_features(9999, conn)


# ---------------------------------------------------------------------------
# New student with no invoices – sensible defaults
# ---------------------------------------------------------------------------

class TestNewStudentDefaults:
    def test_payment_history_ratio_defaults_to_1(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _payment_history_ratio(1, conn) == 1.0

    def test_overdue_invoice_count_defaults_to_0(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _overdue_invoice_count(1, conn) == 0

    def test_total_outstanding_balance_defaults_to_0(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _total_outstanding_balance(1, conn) == 0.0

    def test_historical_default_rate_defaults_to_0(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _historical_default_rate(1, conn) == 0.0

    def test_avg_days_to_pay_defaults_to_0(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _avg_days_to_pay(1, conn) == 0.0

    def test_partial_payment_count_defaults_to_0(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        assert _partial_payment_count(1, conn) == 0

    def test_full_vector_no_nan_for_new_student(self, conn):
        _insert_student(conn, 1, "2023-01-01")
        vec = extract_features(1, conn)
        assert not np.any(np.isnan(vec))
        assert vec[0] == 1.0   # payment_history_ratio
        assert vec[1] == 0.0   # overdue_invoice_count
        assert vec[2] == 0.0   # total_outstanding_balance
        assert vec[4] == 0.0   # historical_default_rate
        assert vec[5] == 0.0   # avg_days_to_pay
        assert vec[6] == 0.0   # partial_payment_count


# ---------------------------------------------------------------------------
# payment_history_ratio
# ---------------------------------------------------------------------------

class TestPaymentHistoryRatio:
    def test_all_paid_on_time(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        # paid_at on the due_date → on time
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-15 10:00:00")
        _insert_invoice(conn, 2, 1, 300, 0, "paid", "2024-02-15", "2024-02-10 10:00:00")
        assert _payment_history_ratio(1, conn) == 1.0

    def test_all_paid_late(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-20 10:00:00")
        _insert_invoice(conn, 2, 1, 300, 0, "paid", "2024-02-15", "2024-02-20 10:00:00")
        assert _payment_history_ratio(1, conn) == 0.0

    def test_mixed_on_time_and_late(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")  # on time
        _insert_invoice(conn, 2, 1, 300, 0, "paid", "2024-02-15", "2024-02-20 10:00:00")  # late
        assert _payment_history_ratio(1, conn) == pytest.approx(0.5)

    def test_unpaid_invoices_not_counted_as_on_time(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "unpaid", "2024-01-15")
        # 1 invoice, 0 paid on time → ratio = 0/1 = 0.0
        assert _payment_history_ratio(1, conn) == 0.0

    def test_no_invoices_returns_1(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        assert _payment_history_ratio(1, conn) == 1.0


# ---------------------------------------------------------------------------
# overdue_invoice_count
# ---------------------------------------------------------------------------

class TestOverdueInvoiceCount:
    def test_no_overdue(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")
        assert _overdue_invoice_count(1, conn) == 0

    def test_one_overdue(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "overdue", "2024-01-15")
        assert _overdue_invoice_count(1, conn) == 1

    def test_multiple_overdue(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "overdue", "2024-01-15")
        _insert_invoice(conn, 2, 1, 300, 300, "overdue", "2024-02-15")
        _insert_invoice(conn, 3, 1, 200, 0, "paid", "2024-03-15", "2024-03-10 10:00:00")
        assert _overdue_invoice_count(1, conn) == 2

    def test_cancelled_not_counted(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "cancelled", "2024-01-15")
        assert _overdue_invoice_count(1, conn) == 0


# ---------------------------------------------------------------------------
# total_outstanding_balance
# ---------------------------------------------------------------------------

class TestTotalOutstandingBalance:
    def test_no_invoices_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        assert _total_outstanding_balance(1, conn) == 0.0

    def test_sums_non_cancelled_invoices(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 200, "unpaid", "2024-01-15")
        _insert_invoice(conn, 2, 1, 300, 300, "overdue", "2024-02-15")
        _insert_invoice(conn, 3, 1, 100, 0, "cancelled", "2024-03-15")
        assert _total_outstanding_balance(1, conn) == pytest.approx(500.0)

    def test_excludes_cancelled(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "cancelled", "2024-01-15")
        assert _total_outstanding_balance(1, conn) == 0.0

    def test_paid_invoice_with_zero_balance(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")
        assert _total_outstanding_balance(1, conn) == 0.0


# ---------------------------------------------------------------------------
# enrollment_duration_days
# ---------------------------------------------------------------------------

class TestEnrollmentDurationDays:
    def test_enrolled_today_is_zero(self, conn):
        today = datetime.date.today().isoformat()
        _insert_student(conn, 1, today)
        result = _enrollment_duration_days(1, conn)
        assert result == 0

    def test_enrolled_one_year_ago(self, conn):
        one_year_ago = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
        _insert_student(conn, 1, one_year_ago)
        result = _enrollment_duration_days(1, conn)
        assert result == 365

    def test_returns_non_negative(self, conn):
        _insert_student(conn, 1, "2015-06-01")
        result = _enrollment_duration_days(1, conn)
        assert result >= 0


# ---------------------------------------------------------------------------
# historical_default_rate
# ---------------------------------------------------------------------------

class TestHistoricalDefaultRate:
    def test_no_invoices_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        assert _historical_default_rate(1, conn) == 0.0

    def test_all_paid_on_time_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")
        assert _historical_default_rate(1, conn) == 0.0

    def test_currently_overdue_counted(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "overdue", "2024-01-15")
        assert _historical_default_rate(1, conn) == 1.0

    def test_paid_late_counted_as_default(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        # paid after due_date → was overdue
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-20 10:00:00")
        assert _historical_default_rate(1, conn) == 1.0

    def test_mixed_default_rate(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")  # on time
        _insert_invoice(conn, 2, 1, 300, 300, "overdue", "2024-02-15")                    # overdue
        assert _historical_default_rate(1, conn) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# avg_days_to_pay
# ---------------------------------------------------------------------------

class TestAvgDaysToPay:
    def test_no_paid_invoices_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "unpaid", "2024-01-15")
        assert _avg_days_to_pay(1, conn) == 0.0

    def test_paid_on_due_date_is_zero_days(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-15 10:00:00")
        assert _avg_days_to_pay(1, conn) == pytest.approx(0.0)

    def test_paid_5_days_late(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-20 10:00:00")
        assert _avg_days_to_pay(1, conn) == pytest.approx(5.0)

    def test_average_of_multiple_invoices(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        # 5 days late + 10 days late = avg 7.5
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-20 10:00:00")
        _insert_invoice(conn, 2, 1, 300, 0, "paid", "2024-02-15", "2024-02-25 10:00:00")
        assert _avg_days_to_pay(1, conn) == pytest.approx(7.5)

    def test_no_invoices_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        assert _avg_days_to_pay(1, conn) == 0.0


# ---------------------------------------------------------------------------
# partial_payment_count
# ---------------------------------------------------------------------------

class TestPartialPaymentCount:
    def test_no_invoices_returns_0(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        assert _partial_payment_count(1, conn) == 0

    def test_fully_paid_invoice_not_counted(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")
        _insert_transaction(conn, 1, 1, 1, 500.0)
        assert _partial_payment_count(1, conn) == 0

    def test_invoice_with_payment_and_remaining_balance(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 200, "unpaid", "2024-01-15")
        _insert_transaction(conn, 1, 1, 1, 300.0)
        assert _partial_payment_count(1, conn) == 1

    def test_invoice_with_no_payment_not_counted(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 500, "unpaid", "2024-01-15")
        assert _partial_payment_count(1, conn) == 0

    def test_multiple_partial_invoices(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        _insert_invoice(conn, 1, 1, 500, 200, "unpaid", "2024-01-15")
        _insert_invoice(conn, 2, 1, 300, 100, "unpaid", "2024-02-15")
        _insert_transaction(conn, 1, 1, 1, 300.0)
        _insert_transaction(conn, 2, 1, 2, 200.0)
        assert _partial_payment_count(1, conn) == 2

    def test_reversal_transaction_not_counted(self, conn):
        _insert_student(conn, 1, "2020-01-01")
        # Invoice with balance > 0 but only a reversal transaction (no payment)
        _insert_invoice(conn, 1, 1, 500, 500, "unpaid", "2024-01-15")
        _insert_transaction(conn, 1, 1, 1, 500.0, txn_type="reversal")
        assert _partial_payment_count(1, conn) == 0


# ---------------------------------------------------------------------------
# extract_features – full vector integration
# ---------------------------------------------------------------------------

class TestExtractFeaturesIntegration:
    def test_feature_order_matches_feature_names(self, conn):
        """Verify each position in the vector corresponds to the correct feature."""
        today = datetime.date.today()
        enroll = (today - datetime.timedelta(days=100)).isoformat()
        _insert_student(conn, 1, enroll)

        # 2 invoices: 1 paid on time, 1 overdue
        _insert_invoice(conn, 1, 1, 500, 0, "paid", "2024-01-15", "2024-01-10 10:00:00")
        _insert_invoice(conn, 2, 1, 300, 300, "overdue", "2024-02-15")
        # 1 partial payment on a third invoice
        _insert_invoice(conn, 3, 1, 200, 100, "unpaid", "2024-03-15")
        _insert_transaction(conn, 1, 1, 3, 100.0)

        vec = extract_features(1, conn)

        assert vec.shape == (7,)
        assert vec.dtype == np.float64

        # payment_history_ratio: 1 on-time out of 3 total = 1/3
        assert vec[0] == pytest.approx(1 / 3)
        # overdue_invoice_count: 1
        assert vec[1] == pytest.approx(1.0)
        # total_outstanding_balance: 300 + 100 = 400 (non-cancelled)
        assert vec[2] == pytest.approx(400.0)
        # enrollment_duration_days: ~100
        assert vec[3] == pytest.approx(100.0, abs=1)
        # historical_default_rate: 1 overdue + 0 paid-late out of 3 = 1/3
        assert vec[4] == pytest.approx(1 / 3)
        # avg_days_to_pay: only 1 paid invoice, paid 5 days early → -5
        assert vec[5] == pytest.approx(-5.0)
        # partial_payment_count: 1
        assert vec[6] == pytest.approx(1.0)
