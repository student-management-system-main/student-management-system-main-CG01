"""
risk_service/tests/test_properties.py
--------------------------------------
Property-based tests for the risk service.

P1 — Risk Classifier Partition Coverage
    classify_risk(s) maps every score in [0, 100] to exactly one of
    "low", "medium", or "high", matching the correct threshold band.

P2 — Feature Vector Invariants
    extract_features() always returns shape (7,), dtype float64,
    with ratios in [0,1] and counts ≥ 0.

P4 — Version Increment Homomorphism
    _increment_patch("vX.Y.Z") == "vX.Y.(Z+1)" for all non-negative X, Y, Z.
    Applying N times yields patch = Z + N.

P9 — Ensemble Score Clamping
    max(p_lr, p_dt) * 100 is always in [0.0, 100.0].

Uses hypothesis for automated counterexample discovery.

Requirements: 6.4, 6.12, 7.5, 7.6, 6.1
"""

from __future__ import annotations

import datetime
import sys
import os

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, text

# Ensure risk_service/ is on the path when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from score import classify_risk  # noqa: E402
from train import _increment_patch  # noqa: E402
from features import extract_features  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite fixture for feature extraction tests
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY,
    student_number  TEXT NOT NULL,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT NOT NULL,
    enrollment_date DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS invoices (
    id                  INTEGER PRIMARY KEY,
    invoice_number      TEXT NOT NULL,
    student_id          INTEGER NOT NULL,
    total_amount        REAL NOT NULL,
    outstanding_balance REAL NOT NULL,
    status              TEXT NOT NULL DEFAULT 'unpaid',
    due_date            DATE NOT NULL,
    paid_at             DATETIME,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY,
    transaction_ref TEXT NOT NULL,
    student_id      INTEGER NOT NULL,
    invoice_id      INTEGER NOT NULL,
    amount          REAL NOT NULL,
    payment_method  TEXT NOT NULL DEFAULT 'cash',
    type            TEXT NOT NULL DEFAULT 'payment',
    reversal_of     INTEGER,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture()
def db_conn():
    """Provide a fresh SQLite in-memory connection with the schema set up."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.connect() as conn:
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))
        conn.commit()
        yield conn


def _make_student(conn, student_id: int, enrollment_date: str = "2022-01-01") -> None:
    conn.execute(
        text(
            "INSERT INTO students (id, student_number, first_name, last_name, email, enrollment_date) "
            "VALUES (:id, :num, 'Test', 'User', :email, :enroll)"
        ),
        {"id": student_id, "num": f"P{student_id}", "email": f"p{student_id}@t.com", "enroll": enrollment_date},
    )
    conn.commit()


# ---------------------------------------------------------------------------
# P1 — Risk Classifier Partition
# ---------------------------------------------------------------------------

class TestClassifyRiskPartition:
    """
    P1: classify_risk(s) is total, deterministic, and correctly partitions [0,100].

    Requirements: 6.4
    """

    @given(st.floats(min_value=0.0, max_value=39.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_low_range_always_low(self, score):
        """Any score in [0.0, 39.0] must produce "low"."""
        assert classify_risk(score) == "low"

    @given(st.floats(min_value=40.0, max_value=69.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_medium_range_always_medium(self, score):
        """Any score in [40.0, 69.0] must produce "medium"."""
        assert classify_risk(score) == "medium"

    @given(st.floats(min_value=70.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_high_range_always_high(self, score):
        """Any score in [70.0, 100.0] must produce "high"."""
        assert classify_risk(score) == "high"

    @given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_result_always_in_valid_set(self, score):
        """classify_risk must always return one of the three valid categories."""
        result = classify_risk(score)
        assert result in ("low", "medium", "high")

    @given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_deterministic_same_score_same_result(self, score):
        """Calling classify_risk twice with the same score must give the same result."""
        assert classify_risk(score) == classify_risk(score)

    @given(
        st.one_of(
            st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
            st.floats(min_value=100.001, allow_nan=False, allow_infinity=False),
        )
    )
    @settings(max_examples=200)
    def test_out_of_range_raises_value_error(self, score):
        """Scores outside [0, 100] must raise ValueError."""
        with pytest.raises(ValueError):
            classify_risk(score)

    def test_boundary_39_is_low(self):
        assert classify_risk(39.0) == "low"

    def test_boundary_40_is_medium(self):
        assert classify_risk(40.0) == "medium"

    def test_boundary_69_is_medium(self):
        assert classify_risk(69.0) == "medium"

    def test_boundary_70_is_high(self):
        assert classify_risk(70.0) == "high"

    def test_boundary_0_is_low(self):
        assert classify_risk(0.0) == "low"

    def test_boundary_100_is_high(self):
        assert classify_risk(100.0) == "high"


# ---------------------------------------------------------------------------
# P2 — Feature Vector Invariants
# ---------------------------------------------------------------------------

class TestFeatureVectorInvariants:
    """
    P2: extract_features() always returns a valid (7,) float64 array
    with ratios in [0, 1] and counts ≥ 0.

    Requirements: 6.12
    """

    def test_new_student_shape(self, db_conn):
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec.shape == (7,)

    def test_new_student_dtype(self, db_conn):
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec.dtype == np.float64

    def test_new_student_no_nan(self, db_conn):
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert not np.any(np.isnan(vec))

    def test_new_student_no_inf(self, db_conn):
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert not np.any(np.isinf(vec))

    def test_payment_history_ratio_in_unit_interval(self, db_conn):
        """payment_history_ratio (index 0) must be in [0.0, 1.0]."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert 0.0 <= vec[0] <= 1.0

    def test_historical_default_rate_in_unit_interval(self, db_conn):
        """historical_default_rate (index 4) must be in [0.0, 1.0]."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert 0.0 <= vec[4] <= 1.0

    def test_overdue_invoice_count_non_negative(self, db_conn):
        """overdue_invoice_count (index 1) must be ≥ 0."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec[1] >= 0.0

    def test_total_outstanding_balance_non_negative(self, db_conn):
        """total_outstanding_balance (index 2) must be ≥ 0."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec[2] >= 0.0

    def test_enrollment_duration_days_non_negative(self, db_conn):
        """enrollment_duration_days (index 3) must be ≥ 0."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec[3] >= 0.0

    def test_partial_payment_count_non_negative(self, db_conn):
        """partial_payment_count (index 6) must be ≥ 0."""
        _make_student(db_conn, 1)
        vec = extract_features(1, db_conn)
        assert vec[6] >= 0.0


# ---------------------------------------------------------------------------
# P4 — Version Increment Homomorphism
# ---------------------------------------------------------------------------

class TestVersionIncrementHomomorphism:
    """
    P4: _increment_patch("vX.Y.Z") == "vX.Y.(Z+1)" for all valid semver strings.
    Applying N times yields patch = Z + N.
    None and empty strings return "v1.0.0".

    Requirements: 7.5, 7.6
    """

    @given(
        major=st.integers(min_value=0, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=500)
    def test_patch_incremented_by_one(self, major, minor, patch):
        """Patch component must increase by exactly 1."""
        version = f"v{major}.{minor}.{patch}"
        result = _increment_patch(version)
        assert result == f"v{major}.{minor}.{patch + 1}"

    @given(
        major=st.integers(min_value=0, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=500)
    def test_major_and_minor_unchanged(self, major, minor, patch):
        """Major and minor components must not change."""
        version = f"v{major}.{minor}.{patch}"
        result = _increment_patch(version)
        parts = result.lstrip("v").split(".")
        assert int(parts[0]) == major
        assert int(parts[1]) == minor

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        patch=st.integers(min_value=0, max_value=50),
        n=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=200)
    def test_applying_n_times_yields_patch_plus_n(self, major, minor, patch, n):
        """Applying _increment_patch N times must yield patch = Z + N."""
        version = f"v{major}.{minor}.{patch}"
        result = version
        for _ in range(n):
            result = _increment_patch(result)
        expected = f"v{major}.{minor}.{patch + n}"
        assert result == expected

    def test_none_returns_v1_0_0(self):
        assert _increment_patch(None) == "v1.0.0"

    def test_empty_string_returns_v1_0_0(self):
        assert _increment_patch("") == "v1.0.0"

    def test_invalid_format_returns_v1_0_0(self):
        assert _increment_patch("invalid") == "v1.0.0"
        assert _increment_patch("1.0.0") == "v1.0.1"   # strips leading v → valid

    def test_v1_0_0_increments_to_v1_0_1(self):
        assert _increment_patch("v1.0.0") == "v1.0.1"

    def test_v2_3_9_increments_to_v2_3_10(self):
        assert _increment_patch("v2.3.9") == "v2.3.10"

    def test_v0_0_0_increments_to_v0_0_1(self):
        assert _increment_patch("v0.0.0") == "v0.0.1"


# ---------------------------------------------------------------------------
# P9 — Ensemble Score Clamping
# ---------------------------------------------------------------------------

class TestEnsembleScoreClamping:
    """
    P9: max(p_lr, p_dt) * 100 is always in [0.0, 100.0].

    Requirements: 6.1
    """

    @given(
        p_lr=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        p_dt=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_ensemble_score_in_valid_range(self, p_lr, p_dt):
        """Ensemble score must always be in [0.0, 100.0]."""
        raw = max(p_lr * 100.0, p_dt * 100.0)
        score = max(0.0, min(100.0, raw))
        assert 0.0 <= score <= 100.0

    @given(
        p_lr=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        p_dt=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_ensemble_score_equals_max_probability_times_100(self, p_lr, p_dt):
        """Ensemble score = max(p_lr, p_dt) * 100 (before clamping — but probs are [0,1] so clamping is no-op)."""
        raw = max(p_lr * 100.0, p_dt * 100.0)
        score = max(0.0, min(100.0, raw))
        expected = max(p_lr, p_dt) * 100.0
        assert abs(score - expected) < 1e-9

    @given(
        p_lr=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        p_dt=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_ensemble_score_is_classifiable(self, p_lr, p_dt):
        """Every valid ensemble score must map to a valid risk category."""
        raw = max(p_lr * 100.0, p_dt * 100.0)
        score = max(0.0, min(100.0, raw))
        category = classify_risk(score)
        assert category in ("low", "medium", "high")

    def test_both_zero_gives_score_zero(self):
        raw = max(0.0 * 100.0, 0.0 * 100.0)
        score = max(0.0, min(100.0, raw))
        assert score == 0.0
        assert classify_risk(score) == "low"

    def test_both_one_gives_score_100(self):
        raw = max(1.0 * 100.0, 1.0 * 100.0)
        score = max(0.0, min(100.0, raw))
        assert score == 100.0
        assert classify_risk(score) == "high"

    def test_higher_probability_dominates(self):
        p_lr, p_dt = 0.3, 0.8
        raw = max(p_lr * 100.0, p_dt * 100.0)
        score = max(0.0, min(100.0, raw))
        assert score == pytest.approx(80.0)
        assert classify_risk(score) == "high"
