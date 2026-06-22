"""
risk_service/features.py
------------------------
Feature extraction for the AI/ML risk scoring pipeline.

Computes a fixed-length feature vector for a given student by querying the
MySQL database.  The vector is consumed by both the Logistic Regression and
Decision Tree models.

Feature column order (must remain stable across model versions):
  0  payment_history_ratio      – proportion of invoices paid on time
  1  overdue_invoice_count       – number of currently overdue invoices
  2  total_outstanding_balance   – sum of outstanding balances (non-cancelled)
  3  enrollment_duration_days    – days since enrollment date
  4  historical_default_rate     – proportion of past invoices that became overdue
  5  avg_days_to_pay             – average days between due date and payment date
  6  partial_payment_count       – number of invoices paid partially

Requirements: 4.3
"""

from __future__ import annotations

import datetime
from typing import Any

import numpy as np
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    "payment_history_ratio",
    "overdue_invoice_count",
    "total_outstanding_balance",
    "enrollment_duration_days",
    "historical_default_rate",
    "avg_days_to_pay",
    "partial_payment_count",
]

NUM_FEATURES: int = len(FEATURE_NAMES)

#: Alias required by the task specification (Requirements: 4.3).
FEATURE_COUNT: int = NUM_FEATURES


def extract_features(student_id: int, db_conn: Any) -> np.ndarray:
    """Extract the feature vector for a single student.

    Args:
        student_id: Primary key of the student record in the ``students``
            table.
        db_conn: An active database connection (e.g. a SQLAlchemy
            ``Connection`` or ``Session``).  The connection is used to
            execute the SQL queries that derive each feature.

    Returns:
        A 1-D ``numpy.ndarray`` of shape ``(7,)`` with ``dtype=float64``
        containing the feature values in the order defined by
        :data:`FEATURE_NAMES`.

    Raises:
        ValueError: If ``student_id`` does not correspond to an existing
            student record.
    """
    _validate_student_exists(student_id, db_conn)

    features = np.array(
        [
            float(_payment_history_ratio(student_id, db_conn)),
            float(_overdue_invoice_count(student_id, db_conn)),
            float(_total_outstanding_balance(student_id, db_conn)),
            float(_enrollment_duration_days(student_id, db_conn)),
            float(_historical_default_rate(student_id, db_conn)),
            float(_avg_days_to_pay(student_id, db_conn)),
            float(_partial_payment_count(student_id, db_conn)),
        ],
        dtype=np.float64,
    )

    return features


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _execute(db_conn: Any, sql: str, params: dict) -> Any:
    """Execute a SQL statement, handling both SQLAlchemy Connection and Session.

    Args:
        db_conn: A SQLAlchemy ``Connection`` or ``Session``.
        sql: Raw SQL string (uses named bind parameters).
        params: Dictionary of bind parameter values.

    Returns:
        The result proxy from the executed statement.
    """
    stmt = text(sql)
    # Session has an execute method; Connection also has execute.
    return db_conn.execute(stmt, params)


def _validate_student_exists(student_id: int, db_conn: Any) -> None:
    """Raise ``ValueError`` if the student does not exist.

    Args:
        student_id: The student primary key to look up.
        db_conn: Active database connection.

    Raises:
        ValueError: When no student with ``student_id`` is found.
    """
    sql = "SELECT id FROM students WHERE id = :student_id"
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    if row is None:
        raise ValueError(f"Student with id={student_id} does not exist.")


def _payment_history_ratio(student_id: int, db_conn: Any) -> float:
    """Compute the proportion of invoices paid on time.

    On-time means the invoice was paid (``paid_at`` is not NULL) and
    ``paid_at <= due_date``.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Float in ``[0.0, 1.0]``.  Returns ``1.0`` when the student has no
        invoices (no evidence of default).
    """
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN paid_at IS NOT NULL
                         AND DATE(paid_at) <= due_date
                    THEN 1
                    ELSE 0
                END
            ) AS on_time
        FROM invoices
        WHERE student_id = :student_id
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    total = int(row[0]) if row and row[0] is not None else 0
    on_time = int(row[1]) if row and row[1] is not None else 0

    if total == 0:
        return 1.0
    return on_time / total


def _overdue_invoice_count(student_id: int, db_conn: Any) -> int:
    """Count currently overdue invoices for the student.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Non-negative integer.
    """
    sql = """
        SELECT COUNT(*) AS cnt
        FROM invoices
        WHERE student_id = :student_id
          AND status = 'overdue'
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _total_outstanding_balance(student_id: int, db_conn: Any) -> float:
    """Sum of outstanding balances across all non-cancelled invoices.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Non-negative float representing the total balance.
        Returns ``0.0`` if no non-cancelled invoices exist.
    """
    sql = """
        SELECT COALESCE(SUM(outstanding_balance), 0.0) AS total_balance
        FROM invoices
        WHERE student_id = :student_id
          AND status != 'cancelled'
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _enrollment_duration_days(student_id: int, db_conn: Any) -> int:
    """Compute the number of days since the student's enrollment date.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Non-negative integer number of days.
    """
    sql = """
        SELECT enrollment_date
        FROM students
        WHERE id = :student_id
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    if row is None or row[0] is None:
        return 0

    enrollment_date = row[0]
    # enrollment_date may be a date object or a string depending on the driver
    if isinstance(enrollment_date, str):
        enrollment_date = datetime.date.fromisoformat(enrollment_date)
    elif isinstance(enrollment_date, datetime.datetime):
        enrollment_date = enrollment_date.date()

    today = datetime.date.today()
    return max(0, (today - enrollment_date).days)


def _historical_default_rate(student_id: int, db_conn: Any) -> float:
    """Compute the proportion of past invoices that became overdue at any point.

    An invoice "became overdue" if its current status is ``overdue`` OR if it
    was ever overdue (i.e. it is now ``paid`` but was previously overdue).
    Since the schema does not store a separate "was_overdue" flag, we use a
    practical proxy: an invoice is counted as having defaulted if its status
    is ``overdue``, OR if it is ``paid`` but ``paid_at > due_date`` (i.e. it
    was paid late, implying it passed through the overdue state).

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Float in ``[0.0, 1.0]``.  Returns ``0.0`` when the student has no
        invoices.
    """
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN status = 'overdue'
                         OR (status = 'paid' AND paid_at IS NOT NULL AND DATE(paid_at) > due_date)
                    THEN 1
                    ELSE 0
                END
            ) AS defaulted
        FROM invoices
        WHERE student_id = :student_id
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    total = int(row[0]) if row and row[0] is not None else 0
    defaulted = int(row[1]) if row and row[1] is not None else 0

    if total == 0:
        return 0.0
    return defaulted / total


def _get_dialect_name(db_conn: Any) -> str:
    """Return the lowercase dialect name for the given connection.

    Supports both SQLAlchemy ``Connection`` (which exposes ``dialect`` via
    ``engine.dialect``) and ``Session`` objects.  Falls back to ``"mysql"``
    when the dialect cannot be determined.

    Args:
        db_conn: A SQLAlchemy ``Connection`` or ``Session``.

    Returns:
        Lowercase dialect name string, e.g. ``"sqlite"`` or ``"mysql"``.
    """
    try:
        # SQLAlchemy Connection: db_conn.dialect
        return db_conn.dialect.name.lower()
    except AttributeError:
        pass
    try:
        # SQLAlchemy Session: db_conn.bind.dialect or db_conn.get_bind().dialect
        bind = getattr(db_conn, "bind", None) or db_conn.get_bind()
        return bind.dialect.name.lower()
    except Exception:
        return "mysql"


def _avg_days_to_pay(student_id: int, db_conn: Any) -> float:
    """Compute the average number of days between due date and payment date.

    Only considers invoices that have been paid (``paid_at IS NOT NULL``).
    Negative values (paid early) are included in the average.

    Uses ``DATEDIFF`` on MySQL and a ``julianday`` expression on SQLite so
    the same code works in both production (MySQL) and test (SQLite) contexts.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Float.  Returns ``0.0`` when no paid invoices exist.
    """
    # Detect dialect to choose the correct date-diff expression.
    dialect_name = _get_dialect_name(db_conn)

    if dialect_name == "sqlite":
        date_diff_expr = "CAST((julianday(DATE(paid_at)) - julianday(due_date)) AS INTEGER)"
    else:
        # MySQL / MariaDB
        date_diff_expr = "DATEDIFF(DATE(paid_at), due_date)"

    sql = f"""
        SELECT AVG({date_diff_expr}) AS avg_days
        FROM invoices
        WHERE student_id = :student_id
          AND paid_at IS NOT NULL
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    if row is None or row[0] is None:
        return 0.0
    return float(row[0])


def _partial_payment_count(student_id: int, db_conn: Any) -> int:
    """Count invoices where at least one payment was made but outstanding_balance > 0.

    An invoice is considered partially paid when:
    - At least one transaction of type ``'payment'`` exists for it, AND
    - Its ``outstanding_balance`` is still greater than zero.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Non-negative integer.
    """
    sql = """
        SELECT COUNT(DISTINCT i.id) AS partial_count
        FROM invoices i
        INNER JOIN transactions t
            ON t.invoice_id = i.id
           AND t.type = 'payment'
        WHERE i.student_id = :student_id
          AND i.outstanding_balance > 0
    """
    row = _execute(db_conn, sql, {"student_id": student_id}).fetchone()
    return int(row[0]) if row and row[0] is not None else 0
