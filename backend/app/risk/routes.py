"""
Risk blueprint routes.

Implements:
    POST /api/v1/risk/batch        — enqueue batch risk scoring (Admin only)
    POST /api/v1/risk/score        — score single student via Risk Service (Admin only)
    POST /api/v1/risk/retrain      — trigger model retraining via Risk Service (Admin only)
    GET  /api/v1/risk/distribution — risk category counts for active students

The student-specific risk read endpoint lives in the students blueprint:
    GET /api/v1/students/:id/risk  — return latest risk score for a student

Requirements: 4.2, 4.5, 4.7, 6.1, 6.2, 6.3, 6.11, 7.1, 7.2, 7.3, 11.5
"""

import requests
from flask import Blueprint, current_app, jsonify, request

from app.auth.decorators import admin_required, get_current_user_id, viewer_or_admin_required

risk_bp = Blueprint("risk", __name__)


# ---------------------------------------------------------------------------
# POST /api/v1/risk/batch
# ---------------------------------------------------------------------------

@risk_bp.route("/batch", methods=["POST"])
@admin_required
def batch_risk_scoring():
    """
    Enqueue a Celery task to batch-score all active students.

    Returns:
        202: {"data": {"message": "Batch risk scoring queued"}}
    """
    from app.risk.tasks import batch_risk_scoring_task  # noqa: PLC0415

    batch_risk_scoring_task.delay()
    return jsonify({"data": {"message": "Batch risk scoring queued"}}), 202


# ---------------------------------------------------------------------------
# POST /api/v1/risk/score
# ---------------------------------------------------------------------------

@risk_bp.route("/score", methods=["POST"])
@admin_required
def score_student_endpoint():
    """
    Score a single student by proxying to the Risk Service.

    Request body (JSON):
        student_id (int, required): the student's primary key

    Returns:
        200: Risk Service response JSON on success
        400: VALIDATION_ERROR if student_id is missing or not an integer
        400/404: pass-through from Risk Service (inactive student / not found)
        503: SERVICE_UNAVAILABLE if Risk Service is unreachable

    Requirements: 6.1, 6.2, 6.3
    """
    from app import db  # noqa: PLC0415
    from app.audit.helpers import write_audit_log  # noqa: PLC0415

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")

    # Validate: must be present and an integer
    if student_id is None or not isinstance(student_id, int):
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "student_id is required and must be an integer.",
                        "details": {"student_id": "required integer field"},
                    }
                }
            ),
            400,
        )

    risk_service_url = current_app.config.get("RISK_SERVICE_URL", "http://risk_service:5001")
    try:
        risk_resp = requests.post(
            f"{risk_service_url}/score",
            json={"student_id": student_id},
            timeout=30,
        )
    except (requests.ConnectionError, requests.Timeout):
        return (
            jsonify(
                {
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Risk Service is unreachable.",
                        "details": {},
                    }
                }
            ),
            503,
        )

    # Pass through 400 / 404 from Risk Service (inactive student, not found)
    if risk_resp.status_code in (400, 404):
        return jsonify(risk_resp.json()), risk_resp.status_code

    # Write audit log on success (do not commit here — write_audit_log only adds to session)
    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="student",
        resource_id=student_id,
        action="risk_score",
    )
    db.session.commit()

    return jsonify(risk_resp.json()), 200


# ---------------------------------------------------------------------------
# POST /api/v1/risk/retrain
# ---------------------------------------------------------------------------

@risk_bp.route("/retrain", methods=["POST"])
@admin_required
def retrain_model():
    """
    Trigger ML model retraining by proxying to the Risk Service.

    Returns:
        200: Risk Service response JSON on success
        503: SERVICE_UNAVAILABLE if Risk Service is unreachable

    Requirements: 7.1, 7.2, 7.3
    """
    from app import db  # noqa: PLC0415
    from app.audit.helpers import write_audit_log  # noqa: PLC0415

    risk_service_url = current_app.config.get("RISK_SERVICE_URL", "http://risk_service:5001")
    try:
        risk_resp = requests.post(
            f"{risk_service_url}/retrain",
            timeout=300,
        )
    except (requests.ConnectionError, requests.Timeout):
        return (
            jsonify(
                {
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Risk Service is unreachable.",
                        "details": {},
                    }
                }
            ),
            503,
        )

    # Write audit log
    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="model",
        resource_id=None,
        action="retrain",
    )
    db.session.commit()

    return jsonify(risk_resp.json()), 200


# ---------------------------------------------------------------------------
# GET /api/v1/risk/distribution
# ---------------------------------------------------------------------------

@risk_bp.route("/distribution", methods=["GET"])
@viewer_or_admin_required
def get_risk_distribution():
    """
    Return risk category counts for all active students based on their most
    recent RiskScore.  Students with no RiskScore are excluded from all counts.

    Uses a subquery to identify the latest RiskScore (MAX computed_at) per
    student, then groups by risk_category.  Missing categories default to 0.

    Returns:
        200: {
            "data": {
                "low_count": N,
                "medium_count": N,
                "high_count": N,
                "total": N
            }
        }

    Invariant: low_count + medium_count + high_count == total

    Requirements: 6.11, 11.5
    """
    from sqlalchemy import func  # noqa: PLC0415

    from app import db  # noqa: PLC0415
    from app.models.risk_score import RiskScore  # noqa: PLC0415
    from app.models.student import Student  # noqa: PLC0415

    # Subquery: latest computed_at per student
    latest_subq = (
        db.session.query(
            RiskScore.student_id,
            func.max(RiskScore.computed_at).label("latest"),
        )
        .group_by(RiskScore.student_id)
        .subquery()
    )

    # Main query: join latest scores to active students, group by category
    rows = (
        db.session.query(RiskScore.risk_category, func.count().label("count"))
        .join(
            latest_subq,
            (RiskScore.student_id == latest_subq.c.student_id)
            & (RiskScore.computed_at == latest_subq.c.latest),
        )
        .join(Student, Student.id == RiskScore.student_id)
        .filter(Student.status == "active")
        .group_by(RiskScore.risk_category)
        .all()
    )

    # Build counts dict; missing categories default to 0
    counts = {row.risk_category: row.count for row in rows}
    low_count = counts.get("low", 0)
    medium_count = counts.get("medium", 0)
    high_count = counts.get("high", 0)
    total = low_count + medium_count + high_count

    return jsonify(
        {
            "data": {
                "low_count": low_count,
                "medium_count": medium_count,
                "high_count": high_count,
                "total": total,
            }
        }
    ), 200
