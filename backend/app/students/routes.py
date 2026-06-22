"""
Student management blueprint.

Endpoints
---------
GET    /api/v1/students                — list with pagination & filters
POST   /api/v1/students                — create a new student
GET    /api/v1/students/<id>           — retrieve a single student
PUT    /api/v1/students/<id>           — update a student (writes audit log)
PATCH  /api/v1/students/<id>/deactivate— deactivate a student (writes audit log)

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from marshmallow import ValidationError
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app import db
from app.auth.decorators import admin_required, get_current_user_id, viewer_or_admin_required
from app.audit.helpers import write_audit_log
from app.models.invoice import Invoice
from app.models.risk_score import RiskScore
from app.models.student import Student
from app.students.schemas import StudentCreateSchema, StudentUpdateSchema

students_bp = Blueprint("students", __name__)

# Reusable schema instances
_create_schema = StudentCreateSchema()
_update_schema = StudentUpdateSchema()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def student_to_dict(
    student: Student,
    risk_category: str | None = None,
    risk_score: float | None = None,
    risk_computed_at=None,
    outstanding_balance: float | None = None,
) -> dict:
    """Serialize a Student ORM object to a plain dict for JSON responses."""
    return {
        "id": student.id,
        "student_number": student.student_number,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "email": student.email,
        "phone": student.phone,
        "enrollment_date": (
            student.enrollment_date.isoformat() if student.enrollment_date else None
        ),
        "status": student.status,
        "sms_enabled": student.sms_enabled,
        "assigned_admin_id": student.assigned_admin_id,
        "risk_category": risk_category,
        "risk_score": str(risk_score) if risk_score is not None else None,
        "risk_computed_at": (
            risk_computed_at.isoformat() if risk_computed_at and hasattr(risk_computed_at, "isoformat") else (str(risk_computed_at) if risk_computed_at else None)
        ),
        "outstanding_balance": str(outstanding_balance) if outstanding_balance is not None else None,
        "created_at": (
            student.created_at.isoformat() if student.created_at else None
        ),
        "updated_at": (
            student.updated_at.isoformat() if student.updated_at else None
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/students
# ---------------------------------------------------------------------------

@students_bp.route("/", methods=["GET"])
@viewer_or_admin_required
def list_students():
    """
    Return a paginated list of students with optional filters.

    Query parameters
    ----------------
    status           : 'active' | 'inactive'
    risk_category    : 'low' | 'medium' | 'high'
    assigned_admin_id: integer
    page             : integer (default 1)
    per_page         : integer (default 20, max 100)

    Requirements: 1.1, 3.8, 3.9
    """
    # --- query params ---
    status_filter = request.args.get("status")
    risk_category_filter = request.args.get("risk_category")
    assigned_admin_filter = request.args.get("assigned_admin_id", type=int)

    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "page and per_page must be integers.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # Clamp per_page to [1, 100]
    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    # Validate status filter
    if status_filter is not None and status_filter not in ("active", "inactive"):
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "status must be 'active' or 'inactive'.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # Validate risk_category filter
    valid_risk_categories = ("low", "medium", "high")
    if risk_category_filter is not None and risk_category_filter not in valid_risk_categories:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "risk_category must be 'low', 'medium', or 'high'.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # --- build latest risk score subquery ---
    latest_risk_subq = (
        db.session.query(
            RiskScore.student_id,
            func.max(RiskScore.computed_at).label("latest_computed_at"),
        )
        .group_by(RiskScore.student_id)
        .subquery()
    )

    # --- build base query with optional risk join ---
    query = (
        db.session.query(Student, RiskScore)
        .outerjoin(
            latest_risk_subq,
            Student.id == latest_risk_subq.c.student_id,
        )
        .outerjoin(
            RiskScore,
            (RiskScore.student_id == latest_risk_subq.c.student_id)
            & (RiskScore.computed_at == latest_risk_subq.c.latest_computed_at),
        )
    )

    if status_filter is not None:
        query = query.filter(Student.status == status_filter)

    if assigned_admin_filter is not None:
        query = query.filter(Student.assigned_admin_id == assigned_admin_filter)

    if risk_category_filter is not None:
        query = query.filter(RiskScore.risk_category == risk_category_filter)

    # --- paginate ---
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    students_data = [
        student_to_dict(
            student,
            risk_category=rs.risk_category if rs else None,
            risk_score=float(rs.score) if rs else None,
            risk_computed_at=rs.computed_at if rs else None,
            outstanding_balance=float(
                db.session.query(
                    db.func.coalesce(db.func.sum(Invoice.outstanding_balance), 0)
                ).filter(
                    Invoice.student_id == student.id,
                    Invoice.status.in_(["unpaid", "overdue"])
                ).scalar() or 0
            ),
        )
        for student, rs in rows
    ]

    return (
        jsonify(
            {
                "data": {
                    "students": students_data,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/students
# ---------------------------------------------------------------------------

@students_bp.route("/", methods=["POST"])
@admin_required
def create_student():
    """
    Create a new student record.

    Returns 201 with the student dict on success.
    Returns 400 with field-level validation errors on failure.

    Requirements: 1.1, 1.2, 1.3
    """
    json_data = request.get_json(silent=True) or {}

    try:
        data = _create_schema.load(json_data)
    except ValidationError as exc:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed.",
                        "details": exc.messages,
                    }
                }
            ),
            400,
        )

    # Check student_number uniqueness
    if Student.query.filter_by(student_number=data["student_number"]).first():
        return (
            jsonify(
                {
                    "error": {
                        "code": "CONFLICT",
                        "message": "A student with this student_number already exists.",
                        "details": {"student_number": data["student_number"]},
                    }
                }
            ),
            409,
        )

    student = Student(
        student_number=data["student_number"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        email=data["email"],
        enrollment_date=data["enrollment_date"],
        phone=data.get("phone"),
        assigned_admin_id=data.get("assigned_admin_id"),
        sms_enabled=data.get("sms_enabled", False),
    )

    db.session.add(student)
    db.session.commit()

    return jsonify({"data": student_to_dict(student)}), 201


# ---------------------------------------------------------------------------
# GET /api/v1/students/<id>
# ---------------------------------------------------------------------------

@students_bp.route("/<int:student_id>", methods=["GET"])
@viewer_or_admin_required
def get_student(student_id: int):
    """
    Retrieve a single student by primary key.

    Returns 404 if the student does not exist.

    Requirements: 1.1
    """
    student = db.session.get(Student, student_id)
    if student is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Student {student_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    # Get latest risk score for this student
    latest_risk = (
        RiskScore.query
        .filter(RiskScore.student_id == student_id)
        .order_by(RiskScore.computed_at.desc())
        .first()
    )

    return jsonify({"data": student_to_dict(
        student,
        risk_category=latest_risk.risk_category if latest_risk else None,
        risk_score=float(latest_risk.score) if latest_risk else None,
    )}), 200


# ---------------------------------------------------------------------------
# GET /api/v1/students/<id>/risk
# ---------------------------------------------------------------------------

@students_bp.route("/<int:student_id>/risk", methods=["GET"])
@viewer_or_admin_required
def get_student_risk(student_id: int):
    """
    Return the latest RiskScore for a student.

    Returns 404 if no risk score exists for the student.

    Requirements: 6.9, 6.10
    """
    student = db.session.get(Student, student_id)
    if student is None:
        return (
            jsonify({"error": {"code": "NOT_FOUND",
                               "message": f"Student {student_id} not found.",
                               "details": {}}}),
            404,
        )

    latest_risk = (
        RiskScore.query
        .filter(RiskScore.student_id == student_id)
        .order_by(RiskScore.computed_at.desc())
        .first()
    )

    if latest_risk is None:
        return (
            jsonify({"error": {"code": "NOT_FOUND",
                               "message": f"No risk score found for student {student_id}.",
                               "details": {}}}),
            404,
        )

    return jsonify({
        "data": {
            "student_id": student_id,
            "score": float(latest_risk.score),
            "risk_category": latest_risk.risk_category,
            "model_version": latest_risk.model_version,
            "computed_at": latest_risk.computed_at.isoformat() if latest_risk.computed_at else None,
        }
    }), 200


# ---------------------------------------------------------------------------
# PUT /api/v1/students/<id>
# ---------------------------------------------------------------------------

@students_bp.route("/<int:student_id>", methods=["PUT"])
@admin_required
def update_student(student_id: int):
    """
    Update a student record and write an audit log entry.

    Requirements: 1.1, 1.3, 1.4
    """
    student = db.session.get(Student, student_id)
    if student is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Student {student_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    json_data = request.get_json(silent=True) or {}

    try:
        data = _update_schema.load(json_data)
    except ValidationError as exc:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed.",
                        "details": exc.messages,
                    }
                }
            ),
            400,
        )

    if not data:
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "No fields provided for update.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # Capture previous values BEFORE applying changes (Requirement 1.4)
    updatable_fields = [
        "first_name", "last_name", "email", "phone",
        "enrollment_date", "assigned_admin_id", "sms_enabled", "status",
    ]
    previous_values: dict = {}
    new_values: dict = {}

    for field in updatable_fields:
        if field in data:
            old_val = getattr(student, field)
            # Serialize dates to ISO strings for JSON storage
            if hasattr(old_val, "isoformat"):
                old_val = old_val.isoformat()
            previous_values[field] = old_val

    # Apply changes
    for field, value in data.items():
        setattr(student, field, value)
        new_val = value
        if hasattr(new_val, "isoformat"):
            new_val = new_val.isoformat()
        new_values[field] = new_val

    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="student",
        resource_id=student_id,
        action="update",
        previous_values=previous_values,
        new_values=new_values,
    )

    db.session.commit()

    return jsonify({"data": student_to_dict(student)}), 200


# ---------------------------------------------------------------------------
# PATCH /api/v1/students/<id>/deactivate
# ---------------------------------------------------------------------------

@students_bp.route("/<int:student_id>/deactivate", methods=["PATCH"])
@admin_required
def deactivate_student(student_id: int):
    """
    Set a student's status to 'inactive' and write an audit log entry.

    Requirements: 1.1, 1.4, 1.5
    """
    student = db.session.get(Student, student_id)
    if student is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Student {student_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    previous_status = student.status
    student.status = "inactive"

    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="student",
        resource_id=student_id,
        action="deactivate",
        previous_values={"status": previous_status},
        new_values={"status": "inactive"},
    )

    db.session.commit()

    return jsonify({"data": student_to_dict(student)}), 200
