"""
risk_service/tests/test_train.py
---------------------------------
Unit tests for the model training pipeline (risk_service/train.py).

Uses an in-memory SQLite database to exercise the full training pipeline
without requiring a live MySQL instance.

Requirements: 4.8
"""

from __future__ import annotations

import datetime
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy import create_engine, text

import train
from train import (
    _increment_patch,
    _get_all_student_ids,
    _get_label,
    _load_registry,
    _save_registry,
    load_active_models,
    train_models,
)


# ---------------------------------------------------------------------------
# SQLite DDL (mirrors test_features.py)
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture()
def tmp_models_dir(tmp_path, monkeypatch):
    """Redirect MODELS_DIR and REGISTRY_PATH to a temporary directory."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(train, "MODELS_DIR", models_dir)
    monkeypatch.setattr(train, "REGISTRY_PATH", models_dir / "registry.json")
    return models_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_student(conn, student_id: int, enrollment_date: str = "2020-01-01") -> None:
    conn.execute(
        text(
            "INSERT INTO students (id, student_number, first_name, last_name, email, enrollment_date, status) "
            "VALUES (:id, :num, :fn, :ln, :email, :enroll, 'active')"
        ),
        {
            "id": student_id,
            "num": f"S{student_id:04d}",
            "fn": "Test",
            "ln": "Student",
            "email": f"student{student_id}@test.com",
            "enroll": enrollment_date,
        },
    )


def _insert_invoice(
    conn,
    invoice_id: int,
    student_id: int,
    status: str,
    due_date: str,
    paid_at: str | None = None,
    balance: float = 0.0,
) -> None:
    conn.execute(
        text(
            "INSERT INTO invoices (id, invoice_number, student_id, total_amount, outstanding_balance, "
            "status, due_date, paid_at) "
            "VALUES (:id, :num, :sid, 500, :balance, :status, :due, :paid)"
        ),
        {
            "id": invoice_id,
            "num": f"INV-{invoice_id:04d}",
            "sid": student_id,
            "balance": balance,
            "status": status,
            "due": due_date,
            "paid": paid_at,
        },
    )


def _populate_students(conn, n_defaulters: int = 10, n_good: int = 10) -> None:
    """Insert enough students to satisfy the minimum sample requirement."""
    sid = 1
    inv_id = 1
    # Defaulters: have an overdue invoice
    for _ in range(n_defaulters):
        _insert_student(conn, sid)
        _insert_invoice(conn, inv_id, sid, "overdue", "2023-01-01", balance=500.0)
        sid += 1
        inv_id += 1
    # Good payers: paid on time
    for _ in range(n_good):
        _insert_student(conn, sid)
        _insert_invoice(conn, inv_id, sid, "paid", "2023-01-01", "2023-01-01 10:00:00")
        sid += 1
        inv_id += 1
    conn.commit()


# ---------------------------------------------------------------------------
# _increment_patch
# ---------------------------------------------------------------------------

class TestIncrementPatch:
    def test_none_returns_initial(self):
        assert _increment_patch(None) == "v1.0.0"

    def test_v1_0_0_becomes_v1_0_1(self):
        assert _increment_patch("v1.0.0") == "v1.0.1"

    def test_v1_0_9_becomes_v1_0_10(self):
        assert _increment_patch("v1.0.9") == "v1.0.10"

    def test_v2_3_5_becomes_v2_3_6(self):
        assert _increment_patch("v2.3.5") == "v2.3.6"

    def test_invalid_format_returns_initial(self):
        assert _increment_patch("invalid") == "v1.0.0"

    def test_two_part_version_returns_initial(self):
        assert _increment_patch("v1.0") == "v1.0.0"

    def test_non_numeric_patch_returns_initial(self):
        assert _increment_patch("v1.0.x") == "v1.0.0"


# ---------------------------------------------------------------------------
# _get_all_student_ids
# ---------------------------------------------------------------------------

class TestGetAllStudentIds:
    def test_empty_table_returns_empty_list(self, conn):
        result = _get_all_student_ids(conn)
        assert result == []

    def test_returns_all_ids(self, conn):
        _insert_student(conn, 1)
        _insert_student(conn, 2)
        _insert_student(conn, 3)
        conn.commit()
        result = _get_all_student_ids(conn)
        assert sorted(result) == [1, 2, 3]


# ---------------------------------------------------------------------------
# _get_label
# ---------------------------------------------------------------------------

class TestGetLabel:
    def test_no_invoices_returns_0(self, conn):
        _insert_student(conn, 1)
        conn.commit()
        assert _get_label(1, conn) == 0

    def test_paid_on_time_returns_0(self, conn):
        _insert_student(conn, 1)
        _insert_invoice(conn, 1, 1, "paid", "2024-01-15", "2024-01-10 10:00:00")
        conn.commit()
        assert _get_label(1, conn) == 0

    def test_overdue_invoice_returns_1(self, conn):
        _insert_student(conn, 1)
        _insert_invoice(conn, 1, 1, "overdue", "2024-01-15", balance=500.0)
        conn.commit()
        assert _get_label(1, conn) == 1

    def test_paid_late_returns_1(self, conn):
        _insert_student(conn, 1)
        _insert_invoice(conn, 1, 1, "paid", "2024-01-15", "2024-01-20 10:00:00")
        conn.commit()
        assert _get_label(1, conn) == 1

    def test_mixed_invoices_returns_1_if_any_default(self, conn):
        _insert_student(conn, 1)
        _insert_invoice(conn, 1, 1, "paid", "2024-01-15", "2024-01-10 10:00:00")  # on time
        _insert_invoice(conn, 2, 1, "overdue", "2024-02-15", balance=300.0)        # overdue
        conn.commit()
        assert _get_label(1, conn) == 1


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

class TestRegistryHelpers:
    def test_load_registry_returns_empty_dict_when_missing(self, tmp_models_dir):
        result = _load_registry()
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_models_dir):
        data = {"version": "v1.0.0", "current_roc_auc": 0.85}
        _save_registry(data)
        loaded = _load_registry()
        assert loaded == data

    def test_save_creates_models_dir(self, tmp_path, monkeypatch):
        new_dir = tmp_path / "new_models"
        monkeypatch.setattr(train, "MODELS_DIR", new_dir)
        monkeypatch.setattr(train, "REGISTRY_PATH", new_dir / "registry.json")
        _save_registry({"version": "v1.0.0"})
        assert new_dir.exists()
        assert (new_dir / "registry.json").exists()


# ---------------------------------------------------------------------------
# train_models – insufficient samples
# ---------------------------------------------------------------------------

class TestTrainModelsInsufficientSamples:
    def test_fewer_than_10_students_returns_error(self, conn, tmp_models_dir):
        # Insert only 5 students
        for i in range(1, 6):
            _insert_student(conn, i)
        conn.commit()

        result = train_models(conn)

        assert result["replaced"] is False
        assert result["n_samples"] < 10
        assert "error" in result

    def test_zero_students_returns_error(self, conn, tmp_models_dir):
        result = train_models(conn)
        assert result["replaced"] is False
        assert result["n_samples"] == 0
        assert "error" in result

    def test_returns_current_roc_auc_from_registry(self, conn, tmp_models_dir):
        _save_registry({"current_roc_auc": 0.75, "version": "v1.0.2"})
        result = train_models(conn)
        assert result["current_roc_auc"] == 0.75


# ---------------------------------------------------------------------------
# train_models – full pipeline
# ---------------------------------------------------------------------------

class TestTrainModelsFull:
    def test_returns_required_keys(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert "new_roc_auc" in result
        assert "current_roc_auc" in result
        assert "replaced" in result
        assert "version" in result
        assert "n_samples" in result

    def test_n_samples_matches_student_count(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert result["n_samples"] == 20

    def test_new_roc_auc_is_float_between_0_and_1(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert isinstance(result["new_roc_auc"], float)
        assert 0.0 <= result["new_roc_auc"] <= 1.0

    def test_first_train_replaces_when_roc_auc_above_zero(self, conn, tmp_models_dir):
        """With no prior model (current_roc_auc=0.0), any positive AUC should replace."""
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        # current_roc_auc starts at 0.0; new model should beat it
        assert result["current_roc_auc"] == 0.0
        assert result["replaced"] is True

    def test_model_files_created_on_replace(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert result["replaced"] is True
        version = result["version"]
        assert (tmp_models_dir / f"model_lr_{version}.joblib").exists()
        assert (tmp_models_dir / f"model_dt_{version}.joblib").exists()
        assert (tmp_models_dir / f"scaler_{version}.joblib").exists()

    def test_registry_updated_on_replace(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert result["replaced"] is True
        registry = _load_registry()
        assert registry["version"] == result["version"]
        assert registry["current_roc_auc"] == result["new_roc_auc"]
        assert registry["active_lr"] is not None
        assert registry["active_dt"] is not None
        assert registry["active_scaler"] is not None
        assert "trained_at" in registry

    def test_version_starts_at_v1_0_0(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert result["replaced"] is True
        assert result["version"] == "v1.0.0"

    def test_version_increments_on_second_train(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result1 = train_models(conn)
        assert result1["version"] == "v1.0.0"

        # Force current_roc_auc to 0 so second train also replaces
        registry = _load_registry()
        registry["current_roc_auc"] = 0.0
        _save_registry(registry)

        result2 = train_models(conn)
        assert result2["replaced"] is True
        assert result2["version"] == "v1.0.1"

    def test_no_replace_when_new_roc_auc_not_better(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        # Set current_roc_auc artificially high so new model cannot beat it
        _save_registry({"current_roc_auc": 1.0, "version": "v5.0.0"})
        result = train_models(conn)
        assert result["replaced"] is False
        assert result["current_roc_auc"] == 1.0

    def test_no_model_files_created_when_not_replaced(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        _save_registry({"current_roc_auc": 1.0, "version": "v5.0.0"})
        train_models(conn)
        # No new joblib files should be created
        joblib_files = list(tmp_models_dir.glob("*.joblib"))
        assert len(joblib_files) == 0


# ---------------------------------------------------------------------------
# load_active_models
# ---------------------------------------------------------------------------

class TestLoadActiveModels:
    def test_raises_file_not_found_when_no_registry(self, tmp_models_dir):
        with pytest.raises(FileNotFoundError, match="registry"):
            load_active_models()

    def test_raises_value_error_when_no_active_models(self, tmp_models_dir):
        _save_registry({"version": None, "active_lr": None, "active_dt": None})
        with pytest.raises(ValueError, match="No active models"):
            load_active_models()

    def test_raises_file_not_found_for_missing_model_file(self, tmp_models_dir):
        _save_registry({
            "active_lr": str(tmp_models_dir / "model_lr_v1.0.0.joblib"),
            "active_dt": str(tmp_models_dir / "model_dt_v1.0.0.joblib"),
            "active_scaler": str(tmp_models_dir / "scaler_v1.0.0.joblib"),
            "version": "v1.0.0",
        })
        with pytest.raises(FileNotFoundError):
            load_active_models()

    def test_returns_models_after_successful_train(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        result = train_models(conn)
        assert result["replaced"] is True

        lr_model, dt_model, scaler, version = load_active_models()

        assert lr_model is not None
        assert dt_model is not None
        assert scaler is not None
        assert version == result["version"]

    def test_loaded_models_can_predict(self, conn, tmp_models_dir):
        _populate_students(conn, n_defaulters=10, n_good=10)
        train_models(conn)

        lr_model, dt_model, scaler, version = load_active_models()

        # Create a dummy feature vector and verify prediction works
        X_dummy = np.array([[0.8, 0, 0.0, 365, 0.0, 2.0, 0]], dtype=np.float64)
        X_scaled = scaler.transform(X_dummy)

        lr_pred = lr_model.predict_proba(X_scaled)
        dt_pred = dt_model.predict_proba(X_scaled)

        assert lr_pred.shape == (1, 2)
        assert dt_pred.shape == (1, 2)
        # Probabilities must sum to 1
        assert abs(lr_pred[0].sum() - 1.0) < 1e-6
        assert abs(dt_pred[0].sum() - 1.0) < 1e-6
