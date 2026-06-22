"""
Marshmallow schemas for Transaction request validation.

``TransactionCreateSchema`` — validates the POST /api/v1/transactions payload.

Requirements: 3.1, 3.3
"""

from decimal import Decimal

from marshmallow import Schema, ValidationError, fields, validate, validates


class TransactionCreateSchema(Schema):
    """Validate the body of POST /api/v1/transactions."""

    # Required fields
    student_id = fields.Integer(required=True)
    invoice_id = fields.Integer(required=True)
    amount = fields.Decimal(
        required=True,
        places=2,
        as_string=False,
    )
    payment_method = fields.String(
        required=True,
        validate=validate.Length(min=1, max=50),
    )

    @validates("amount")
    def validate_amount(self, value: Decimal) -> Decimal:
        """Ensure amount is strictly greater than zero (Requirement 3.3)."""
        if value <= 0:
            raise ValidationError("amount must be greater than 0.")
        return value
