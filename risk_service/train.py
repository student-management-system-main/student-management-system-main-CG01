"""
risk_service/train.py
---------------------
Model training pipeline for the AI/ML risk scoring service.

Trains a Logistic Regression and a Decision Tree classifier on historical
transaction and invoice data.  Persists the trained models to the
``models/`` directory using joblib and updates ``models/registry.json`` only
when the new model's cross-validated ROC-AUC exceeds the current model's
ROC-AUC.

Training pipeline (per design document):
  1. Extract feature matrix ``X`` and label vector ``y`` for all historical
     records (label 1 = defaulted, 0 = paid on time).
  2. Stratified 80/20 train/test split.
  3. Apply ``StandardScaler`` to features.
  4. Train ``LogisticRegression(max_iter=1000, C=1.0)`` and
     ``DecisionTreeClassifier(max_depth=8)``.
  5. Evaluate both models with 5-fold cross-validated ROC-AUC.
  6. Persist models as ``models/model_lr_v{version}.joblib`` and
     ``models/model_dt_v{version}.joblib``.
  7. Replace active model only when new ROC-AUC > current ROC-AUC.

Requirements: 4.8
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Tuple

import joblib
import numpy as np
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODELS_DIR: Path = Path(__file__).parent / "models"
REGISTRY_PATH: Path = MODELS_DIR / "registry.json"

_INITIAL_VERSION = "v1.0.0"
_MIN_SAMPLES = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def train_models(db_conn: Any) -> dict[str, Any]:
    """Train Logistic Regression and Decision Tree models.

    Extracts features from the database, trains both models, evaluates them
    with 5-fold cross-validated ROC-AUC, and persists the models to disk.
    The active model registry is updated only when the new ROC-AUC exceeds
    the current model's ROC-AUC.

    Args:
        db_conn: An active database connection used to extract training data.

    Returns:
        A dictionary with keys:
          - ``new_roc_auc`` (float): Cross-validated ROC-AUC of the newly
            trained models.
          - ``current_roc_auc`` (float): ROC-AUC of the previously active
            models (0.0 if no model existed).
          - ``replaced`` (bool): ``True`` when the new model replaced the
            active model.
          - ``version`` (str): Version string assigned to the new models.
          - ``n_samples`` (int): Number of training samples used.

    Requirements: 4.8
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score

    from features import extract_features

    # ------------------------------------------------------------------
    # 1. Extract feature matrix X and label vector y
    # ------------------------------------------------------------------
    student_ids = _get_all_student_ids(db_conn)
    n_samples = len(student_ids)

    if n_samples < _MIN_SAMPLES:
        registry = _load_registry()
        current_roc_auc = float(registry.get("current_roc_auc") or 0.0)
        version = registry.get("version") or _INITIAL_VERSION
        return {
            "new_roc_auc": 0.0,
            "current_roc_auc": current_roc_auc,
            "replaced": False,
            "version": version,
            "n_samples": n_samples,
            "error": f"Insufficient samples: need at least {_MIN_SAMPLES}, got {n_samples}",
        }

    X_list = []
    y_list = []
    for sid in student_ids:
        try:
            features = extract_features(sid, db_conn)
            label = _get_label(sid, db_conn)
            X_list.append(features)
            y_list.append(label)
        except Exception:
            # Skip students whose features cannot be extracted
            continue

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.int32)
    n_samples = len(y)

    if n_samples < _MIN_SAMPLES:
        registry = _load_registry()
        current_roc_auc = float(registry.get("current_roc_auc") or 0.0)
        version = registry.get("version") or _INITIAL_VERSION
        return {
            "new_roc_auc": 0.0,
            "current_roc_auc": current_roc_auc,
            "replaced": False,
            "version": version,
            "n_samples": n_samples,
            "error": f"Insufficient samples after extraction: need at least {_MIN_SAMPLES}, got {n_samples}",
        }

    # ------------------------------------------------------------------
    # 2. Stratified 80/20 train/test split
    # ------------------------------------------------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # ------------------------------------------------------------------
    # 3. Apply StandardScaler (fit on train, transform both)
    # ------------------------------------------------------------------
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ------------------------------------------------------------------
    # 4. Train models
    # ------------------------------------------------------------------
    lr_model = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    lr_model.fit(X_train_scaled, y_train)

    dt_model = DecisionTreeClassifier(max_depth=8, random_state=42)
    dt_model.fit(X_train_scaled, y_train)

    # ------------------------------------------------------------------
    # 5. Evaluate with 5-fold cross-validated ROC-AUC
    # ------------------------------------------------------------------
    lr_cv_scores = cross_val_score(
        LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        X_train_scaled, y_train, cv=5, scoring="roc_auc"
    )
    dt_cv_scores = cross_val_score(
        DecisionTreeClassifier(max_depth=8, random_state=42),
        X_train_scaled, y_train, cv=5, scoring="roc_auc"
    )

    new_roc_auc = float(np.mean([np.mean(lr_cv_scores), np.mean(dt_cv_scores)]))

    # ------------------------------------------------------------------
    # 6. Retraining guard – compare against current active model
    # ------------------------------------------------------------------
    registry = _load_registry()
    current_roc_auc = float(registry.get("current_roc_auc") or 0.0)

    replaced = new_roc_auc > current_roc_auc

    if replaced:
        # Determine next version
        current_version = registry.get("version") or None
        new_version = _increment_patch(current_version)

        # Persist models and scaler
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        lr_path = MODELS_DIR / f"model_lr_{new_version}.joblib"
        dt_path = MODELS_DIR / f"model_dt_{new_version}.joblib"
        scaler_path = MODELS_DIR / f"scaler_{new_version}.joblib"

        joblib.dump(lr_model, lr_path)
        joblib.dump(dt_model, dt_path)
        joblib.dump(scaler, scaler_path)

        # Update registry
        registry["active_lr"] = str(lr_path)
        registry["active_dt"] = str(dt_path)
        registry["active_scaler"] = str(scaler_path)
        registry["version"] = new_version
        registry["current_roc_auc"] = new_roc_auc
        registry["trained_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        _save_registry(registry)
    else:
        new_version = registry.get("version") or _INITIAL_VERSION

    return {
        "new_roc_auc": new_roc_auc,
        "current_roc_auc": current_roc_auc,
        "replaced": replaced,
        "version": new_version,
        "n_samples": n_samples,
    }


def load_active_models() -> Tuple[Any, Any, Any, str]:
    """Load the currently active LR model, DT model, scaler, and version.

    Reads ``models/registry.json`` and loads the joblib files referenced by
    the ``active_lr``, ``active_dt``, and ``active_scaler`` fields.

    Returns:
        A tuple ``(lr_model, dt_model, scaler, version)`` where each model
        and scaler is the deserialized scikit-learn object, and ``version``
        is the version string from the registry.

    Raises:
        FileNotFoundError: If the registry does not exist or any referenced
            model file is missing.
        ValueError: If the registry has no active models recorded.

    Requirements: 4.8
    """
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Model registry not found at {REGISTRY_PATH}. "
            "Run train_models() first."
        )

    registry = _load_registry()

    lr_path = registry.get("active_lr")
    dt_path = registry.get("active_dt")
    scaler_path = registry.get("active_scaler")
    version = registry.get("version")

    if not lr_path or not dt_path or not scaler_path:
        raise ValueError(
            "No active models found in registry. Run train_models() first."
        )

    for path, label in [(lr_path, "LR model"), (dt_path, "DT model"), (scaler_path, "scaler")]:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"{label} file not found: {path}. "
                "The registry may be stale — run train_models() again."
            )

    lr_model = joblib.load(lr_path)
    dt_model = joblib.load(dt_path)
    scaler = joblib.load(scaler_path)

    return lr_model, dt_model, scaler, version


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_all_student_ids(db_conn: Any) -> list[int]:
    """Query all student IDs from the students table.

    Args:
        db_conn: Active database connection.

    Returns:
        List of integer student IDs.
    """
    result = db_conn.execute(text("SELECT id FROM students"))
    return [row[0] for row in result.fetchall()]


def _get_label(student_id: int, db_conn: Any) -> int:
    """Derive the binary label for a student.

    Label = 1 if the student has any overdue or late-paid invoices
    (i.e. ``historical_default_rate > 0``), else 0.

    Args:
        student_id: Student primary key.
        db_conn: Active database connection.

    Returns:
        Integer 0 or 1.
    """
    sql = """
        SELECT COUNT(*) AS defaulted
        FROM invoices
        WHERE student_id = :student_id
          AND (
              status = 'overdue'
              OR (status = 'paid' AND paid_at IS NOT NULL AND DATE(paid_at) > due_date)
          )
    """
    row = db_conn.execute(text(sql), {"student_id": student_id}).fetchone()
    defaulted = int(row[0]) if row and row[0] is not None else 0
    return 1 if defaulted > 0 else 0


def _increment_patch(version: str | None) -> str:
    """Increment the patch component of a semantic version string.

    If ``version`` is ``None`` or cannot be parsed, returns ``"v1.0.0"``.

    Args:
        version: Version string in the format ``"v{major}.{minor}.{patch}"``.

    Returns:
        New version string with patch incremented by 1.

    Examples:
        >>> _increment_patch(None)
        'v1.0.0'
        >>> _increment_patch('v1.0.0')
        'v1.0.1'
        >>> _increment_patch('v2.3.9')
        'v2.3.10'
    """
    if version is None:
        return _INITIAL_VERSION

    # Strip leading 'v'
    raw = version.lstrip("v")
    parts = raw.split(".")
    if len(parts) != 3:
        return _INITIAL_VERSION

    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return _INITIAL_VERSION

    return f"v{major}.{minor}.{patch + 1}"


def _load_registry() -> dict[str, Any]:
    """Load the model registry from ``models/registry.json``.

    Returns:
        Registry dictionary.  Returns an empty dict when the file does not
        exist.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        return {}
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_registry(registry: dict[str, Any]) -> None:
    """Persist the model registry to ``models/registry.json``.

    Args:
        registry: Registry dictionary to serialise.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2)


def get_active_model_paths() -> dict[str, str | None]:
    """Return the file paths of the currently active models.

    Returns:
        Dictionary with keys ``"lr"``, ``"dt"``, ``"scaler"``, and
        ``"version"`` mapping to the path strings from the registry, or
        ``None`` when no active model exists.
    """
    registry = _load_registry()
    return {
        "lr": registry.get("active_lr"),
        "dt": registry.get("active_dt"),
        "scaler": registry.get("active_scaler"),
        "version": registry.get("version"),
    }
