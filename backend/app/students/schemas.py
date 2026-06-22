"""
Marshmallow schemas for Student request validation.

``StudentCreateSchema`` — validates the POST /students payload.
``StudentUpdateSchema`` — validates the PUT /students/:id payload (all fields
optional).

Requirements: 1.1, 1.2, 1.3
"""

from marshmallow import Schema, ValidationError, fields, validate, validates


class StudentCreateSchema(Schema):
    """Validate the body of POST /api/v1/students."""

    # Required fields
    student_number = fields.String(
        required=True,
        validate=validate.Length(min=1, max=50),
    )
    first_name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    last_name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255),
    )
    enrollment_date = fields.Date(
        required=True,
        format="iso",  # expects YYYY-MM-DD
    )

    # Optional fields
    phone = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.Length(max=30),
    )
    assigned_admin_id = fields.Integer(
        load_default=None,
        allow_none=True,
    )
    sms_enabled = fields.Boolean(load_default=False)


class StudentUpdateSchema(Schema):
    """Validate the body of PUT /api/v1/students/:id.

    All fields are optional; only those present will be updated.
    """

    first_name = fields.String(
        validate=validate.Length(min=1, max=100),
    )
    last_name = fields.String(
        validate=validate.Length(min=1, max=100),
    )
    email = fields.Email(
        validate=validate.Length(max=255),
    )
    phone = fields.String(
        allow_none=True,
        validate=validate.Length(max=30),
    )
    enrollment_date = fields.Date(format="iso")
    assigned_admin_id = fields.Integer(allow_none=True)
    sms_enabled = fields.Boolean()
    status = fields.String(
        validate=validate.OneOf(["active", "inactive"]),
    )

    @validates("status")
    def validate_status(self, value: str) -> str:
        """Prevent arbitrary status updates via PUT (use /deactivate instead)."""
        allowed = {"active", "inactive"}
        if value not in allowed:
            raise ValidationError(
                f"status must be one of: {', '.join(sorted(allowed))}"
            )
        return value
