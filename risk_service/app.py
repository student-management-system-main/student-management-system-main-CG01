"""
risk_service/app.py
-------------------
Flask application factory and endpoint definitions for the AI/ML Risk Scoring
micro-service.

Exposes four endpoints:
  POST /score         – Score a single student and return their risk result.
  POST /score/batch   – Score all active students (scheduled batch run).
  POST /retrain       – Trigger model retraining; replace active models only
                        when the new ROC-AUC exceeds the current one.
  GET  /health        – Liveness check.

Configuration is read from environment variables via :class:`config.Config`:
  DB_URL              – SQLAlchemy database URL
  MODEL_DIR           – Path to the directory containing trained model files
  RISK_SERVICE_PORT   – TCP port the service listens on (default: 5001)

Requirements: 4.1, 4.2, 4.7
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request


def create_app() -> Flask:
    """Application factory for the risk scoring service.

    Reads configuration from environment variables (via :class:`config.Config`)
    and registers all route handlers and JSON error handlers.

    Returns:
        A configured :class:`flask.Flask` application instance.
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Load config from environment
    # ------------------------------------------------------------------
    from config import Config  # noqa: PLC0415

    app.config["DB_URL"] = Config.DB_URL
    app.config["MODEL_DIR"] = str(Config.MODEL_DIR)
    app.config["RISK_SERVICE_PORT"] = Config.RISK_SERVICE_PORT

    # ------------------------------------------------------------------
    # Error handlers – always return JSON
    # ------------------------------------------------------------------

    @app.errorhandler(400)
    def bad_request(exc):
        return jsonify({"error": {"code": "BAD_REQUEST", "message": str(exc)}}), 400

    @app.errorhandler(404)
    def not_found(exc):
        return jsonify({"error": {"code": "NOT_FOUND", "message": str(exc)}}), 404

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": str(exc)}}), 405

    @app.errorhandler(500)
    def internal_error(exc):
        return jsonify({"error": {"code": "INTERNAL_SERVER_ERROR",
                                  "message": "An unexpected error occurred"}}), 500

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health")
    def health():
        """Liveness check endpoint.

        Returns:
            JSON ``{"status": "ok"}`` with HTTP 200.
        """
        return jsonify({"status": "ok"}), 200

    @app.post("/score")
    def score():
        """Score a single student.

        Expected JSON body::

            {"student_id": <int>}

        Validates that ``student_id`` is present and is an integer, then
        creates a SQLAlchemy connection from ``app.config["DB_URL"]``, calls
        ``score_student(student_id, db_conn=conn)``, and returns the result.

        Returns:
            JSON with ``student_id``, ``score``, ``risk_category``,
            ``model_version``, and ``computed_at`` with HTTP 200.

        Requirements: 4.1, 4.7
        """
        data = request.get_json(force=True) or {}
        student_id = data.get("student_id")

        # Validate student_id is present
        if student_id is None:
            return jsonify({"error": {"code": "VALIDATION_ERROR",
                                      "message": "student_id is required"}}), 400

        # Validate student_id is an integer (reject booleans, floats, strings)
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            return jsonify({"error": {"code": "VALIDATION_ERROR",
                                      "message": "student_id must be an integer"}}), 400

        from sqlalchemy import create_engine  # noqa: PLC0415
        from score import score_student  # noqa: PLC0415

        engine = create_engine(app.config["DB_URL"])
        with engine.connect() as conn:
            result = score_student(student_id, db_conn=conn)
        return jsonify(result), 200

    @app.post("/score/batch")
    def score_batch():
        """Score all active students.

        Creates a DB connection from ``app.config["DB_URL"]``, queries all
        active student IDs (``status = 'active'``), calls
        ``score_student(student_id, db_conn)`` for each, and tracks successes
        and failures.

        Returns:
            JSON with:
              - ``scored_count`` (int): Number of students successfully scored.
              - ``failed_count`` (int): Number of students that failed to score.
              - ``errors`` (list): List of ``{"student_id": int, "error": str}``
                dicts for each failure.

        Requirements: 4.2, 4.7
        """
        from sqlalchemy import create_engine, text  # noqa: PLC0415
        from score import score_student  # noqa: PLC0415

        engine = create_engine(app.config["DB_URL"])

        scored_count = 0
        failed_count = 0
        errors = []

        with engine.connect() as conn:
            # Query all active student IDs
            result = conn.execute(
                text("SELECT id FROM students WHERE status = 'active'")
            )
            student_ids = [row[0] for row in result.fetchall()]

            # Score each active student
            for student_id in student_ids:
                try:
                    score_student(student_id, db_conn=conn)
                    scored_count += 1
                except Exception as exc:
                    failed_count += 1
                    errors.append({
                        "student_id": int(student_id),
                        "error": str(exc),
                    })

        return jsonify({
            "scored_count": scored_count,
            "failed_count": failed_count,
            "errors": errors,
        }), 200

    @app.post("/retrain")
    def retrain():
        """Trigger model retraining.

        Creates a DB connection from ``app.config["DB_URL"]``, calls
        ``train_models(db_conn)`` from ``train.py``, and returns the result
        dict directly.

        Retrains Logistic Regression and Decision Tree models on the latest
        data.  Replaces the active model only when the new cross-validated
        ROC-AUC exceeds the current model's ROC-AUC.

        Returns:
            JSON with ``new_roc_auc``, ``current_roc_auc``, ``replaced``,
            ``version``, and ``n_samples`` with HTTP 200.

        Requirements: 4.7
        """
        from sqlalchemy import create_engine  # noqa: PLC0415
        from train import train_models  # noqa: PLC0415

        engine = create_engine(app.config["DB_URL"])
        with engine.connect() as conn:
            result = train_models(db_conn=conn)
        return jsonify(result), 200

    return app


if __name__ == "__main__":
    application = create_app()
    from config import Config  # noqa: PLC0415
    application.run(host="0.0.0.0", port=Config.RISK_SERVICE_PORT, debug=False)
