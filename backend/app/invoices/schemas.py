
"""
Marshmallow schemas for Invoice request validation.

``InvoiceCreateSchema`` — validates the POST /api/v1/invoices payload.

Requirements: 2.2, 2.3
"""

import re

from marshmallow import Schema, ValidationError, fields, validate, validates


class InvoiceCreateSchema(Schema):
    """Validate the body of POST /api/v1/invoices."""

    # Required fields
    student_id = fields.Integer(
        required=True,
        strict=True,
    )
    fee_type_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, error="fee_type_ids must contain at least one fee type ID."),
    )
    billing_period = fields.String(
        required=True,
    )

    @validates("billing_period")
    def validate_billing_period(self, value: str) -> str:
        """Ensure billing_period matches YYYY-MM format."""
        pattern = r"^\d{4}-(0[1-9]|1[0-2])$"
        if not re.match(pattern, value):
            raise ValidationError(
                'billing_period must be in "YYYY-MM" format (e.g. "2024-01").'
            )
        return value

    @validates("student_id")
    def validate_student_id(self, value: int) -> int:
        """Ensure student_id is positive."""
        if value <= 0:
            raise ValidationError("student_id must be a positive integer.")
        return value
