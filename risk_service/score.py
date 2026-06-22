"""
risk_service/score.py
---------------------
Scoring module for the AI/ML risk scoring service.

Loads the active Logistic Regression and Decision Tree models from the model
registry, extracts features for a given student, and computes a final risk
score using the ensemble rule:

    final_score = max(lr_probability * 100, dt_probability * 100)

Risk category thresholds (Requirements 4.1, 4.4):
  0  – 39  → "low"
  40 – 69  → "medium"
  70 – 100 → "high"

Requirements: 4.1, 4.4
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import create_engine, text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_student(student_id: int, db_conn: Any = None) -> dict[str, Any]:
    """Compute the risk score for a single student.

    Loads the active LR and DT models from ``models/registry.json``, extracts
    the feature vector for ``student_id``, and returns the ensemble score
    together with the derived risk category.  The result is persisted to the
    ``risk_scores`` table.

    The ensemble rule is::

        final_score = max(lr_probability * 100, dt_probability * 100)

    Args:
        student_id: Primary key of the student record.
        db_conn: Active SQLAlchemy database connection.  When ``None``, a new
            connection is created from :attr:`config.Config.DB_URL`.

    Returns:
        A dictionary with keys:
          - ``student_id`` (int)
          - ``score`` (float): Value in ``[0.0, 100.0]``.
          - ``risk_category`` (str): One of ``"low"``, ``"medium"``,
            ``"high"``.
          - ``model_version`` (str): Version tag from the registry, or
            ``"none"`` when no models are trained yet.
          - ``computed_at`` (str): ISO-8601 UTC timestamp.

    Requirements: 4.1, 4.4
    """
    from train import load_active_models  # noqa: PLC0415
    from features import extract_features  # noqa: PLC0415

    # ------------------------------------------------------------------
    # 1. Create a DB connection if one was not provided
    # ------------------------------------------------------------------
    _owns_conn = False
    if db_conn is None:
        from config import Config  # noqa: PLC0415
        engine = create_engine(Config.DB_URL)
        db_conn = engine.connect()
        _owns_conn = True

    try:
        # ------------------------------------------------------------------
        # 2. Load active models – return stub if none are trained yet
        # ------------------------------------------------------------------
        try:
            lr_model, dt_model, scaler, version = load_active_models()
        except (FileNotFoundError, ValueError):
            computed_at = datetime.datetime.utcnow().isoformat() + "Z"
            return {
                "student_id": int(student_id),
                "score": 0.0,
                "risk_category": "low",
                "model_version": "none",
                "computed_at": computed_at,
            }

        # ------------------------------------------------------------------
        # 3. Extract features
        # ------------------------------------------------------------------
        features = extract_features(student_id, db_conn)

        # ------------------------------------------------------------------
        # 4. Scale features
        # ------------------------------------------------------------------
        X_scaled = scaler.transform(features.reshape(1, -1))

        # ------------------------------------------------------------------
        # 5. Get probabilities from both models (probability of class 1)
        # ------------------------------------------------------------------
        lr_prob = lr_model.predict_proba(X_scaled)[0][1]
        dt_prob = dt_model.predict_proba(X_scaled)[0][1]

        # ------------------------------------------------------------------
        # 6. Compute final score – clamp to [0.0, 100.0]
        # ------------------------------------------------------------------
        final_score = float(max(lr_prob * 100.0, dt_prob * 100.0))
        final_score = max(0.0, min(100.0, final_score))

        # ------------------------------------------------------------------
        # 7. Classify risk category
        # ------------------------------------------------------------------
        risk_category = classify_risk(final_score)

        # ------------------------------------------------------------------
        # 8. Persist result to risk_scores table
        # ------------------------------------------------------------------
        computed_at_dt = datetime.datetime.utcnow()
        computed_at_str = computed_at_dt.isoformat() + "Z"

        insert_sql = text(
            """
            INSERT INTO risk_scores
                (student_id, score, risk_category, model_version, computed_at)
            VALUES
                (:student_id, :score, :risk_category, :model_version, :computed_at)
            """
        )
        db_conn.execute(
            insert_sql,
            {
                "student_id": int(student_id),
                "score": final_score,
                "risk_category": risk_category,
                "model_version": version,
                "computed_at": computed_at_dt,
            },
        )
        # Commit if the connection supports it (raw Connection vs Session)
        if hasattr(db_conn, "commit"):
            db_conn.commit()

        # ------------------------------------------------------------------
        # 9. Return result dict
        # ------------------------------------------------------------------
        return {
            "student_id": int(student_id),
            "score": final_score,
            "risk_category": risk_category,
            "model_version": version,
            "computed_at": computed_at_str,
        }

    finally:
        if _owns_conn:
            db_conn.close()


def classify_risk(score: float) -> str:
    """Classify a numeric risk score into a risk category.

    Thresholds (inclusive on both ends of each range):
      - ``0``  – ``39``  → ``"low"``
      - ``40`` – ``69``  → ``"medium"``
      - ``70`` – ``100`` → ``"high"``

    Args:
        score: A numeric value in the range ``[0.0, 100.0]``.

    Returns:
        One of the strings ``"low"``, ``"medium"``, or ``"high"``.

    Raises:
        ValueError: If ``score`` is outside the range ``[0, 100]``.

    Examples:
        >>> classify_risk(0)
        'low'
        >>> classify_risk(39)
        'low'
        >>> classify_risk(40)
        'medium'
        >>> classify_risk(69)
        'medium'
        >>> classify_risk(70)
        'high'
        >>> classify_risk(100)
        'high'
    """
    if score < 0 or score > 100:
        raise ValueError(f"score must be in [0, 100], got {score!r}")

    if score <= 39:
        return "low"
    if score <= 69:
        return "medium"
    return "high"
