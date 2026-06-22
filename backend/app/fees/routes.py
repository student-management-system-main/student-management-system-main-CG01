"""
Fee type management blueprint.

Endpoints
---------
GET  /api/v1/fee-types        — list fee types filtered by is_active
POST /api/v1/fee-types        — create a new fee type
PUT  /api/v1/fee-types/<id>   — update an existing fee type

Requirements: 2.1
"""

from marshmallow import ValidationError
from flask import Blueprint, jsonify, request

from app import db
from app.auth.decorators import admin_required, viewer_or_admin_required
from app.models.fee_type import FeeType
from app.fees.schemas import FeeTypeCreateSchema, FeeTypeUpdateSchema

fees_bp = Blueprint("fees", __name__)

# Reusable schema instances
_create_schema = FeeTypeCreateSchema()
_update_schema = FeeTypeUpdateSchema()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def fee_type_to_dict(fee_type: FeeType) -> dict:
    """Serialize a FeeType ORM object to a plain dict for JSON responses."""
    return {
        "id": fee_type.id,
        "name": fee_type.name,
        "description": fee_type.description,
        # Decimal serialized as string to preserve precision
        "amount": str(fee_type.amount),
        "currency": fee_type.currency,
        "due_date": (
            fee_type.due_date.isoformat() if fee_type.due_date else None
        ),
        "is_active": fee_type.is_active,
        "created_at": (
            fee_type.created_at.isoformat() if fee_type.created_at else None
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/fee-types
# ---------------------------------------------------------------------------

@fees_bp.route("/", methods=["GET"])
@viewer_or_admin_required
def list_fee_types():
    """
    Return all fee types, optionally filtered by is_active status.

    Query parameters
    ----------------
    is_active : bool (default True)
        Pass ``false`` to retrieve inactive fee types instead.

    Requirements: 2.1
    """
    # Parse is_active query param; default to True
    is_active_raw = request.args.get("is_active", "true").lower()
    if is_active_raw in ("true", "1", "yes"):
        is_active = True
    elif is_active_raw in ("false", "0", "no"):
        is_active = False
    else:
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "is_active must be a boolean value (true or false).",
                        "details": {},
                    }
                }
            ),
            400,
        )

    fee_types = FeeType.query.filter_by(is_active=is_active).all()

    return (
        jsonify(
            {
                "data": {
                    "fee_types": [fee_type_to_dict(ft) for ft in fee_types],
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/fee-types
# ---------------------------------------------------------------------------

@fees_bp.route("/", methods=["POST"])
@admin_required
def create_fee_type():
    """
    Create a new fee type record.

    Returns 201 with the fee type dict on success.
    Returns 400 with field-level validation errors on failure.

    Requirements: 2.1
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

    fee_type = FeeType(
        name=data["name"],
        description=data.get("description"),
        amount=data["amount"],
        currency=data.get("currency", "USD"),
        due_date=data["due_date"],
        is_active=data.get("is_active", True),
    )

    db.session.add(fee_type)
    db.session.commit()

    return jsonify({"data": fee_type_to_dict(fee_type)}), 201


# ---------------------------------------------------------------------------
# PUT /api/v1/fee-types/<id>
# ---------------------------------------------------------------------------

@fees_bp.route("/<int:fee_type_id>", methods=["PUT"])
@admin_required
def update_fee_type(fee_type_id: int):
    """
    Update an existing fee type record.

    Returns 404 if the fee type does not exist.
    Returns 400 with field-level validation errors on failure.

    Requirements: 2.1
    """
    fee_type = db.session.get(FeeType, fee_type_id)
    if fee_type is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Fee type {fee_type_id} not found.",
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

    # Apply updates
    for field, value in data.items():
        setattr(fee_type, field, value)

    db.session.commit()

    return jsonify({"data": fee_type_to_dict(fee_type)}), 200
