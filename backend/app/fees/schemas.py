"""
Marshmallow schemas for FeeType request validation.

``FeeTypeCreateSchema`` — validates the POST /api/v1/fee-types payload.
``FeeTypeUpdateSchema`` — validates the PUT /api/v1/fee-types/:id payload
                          (all fields optional).

Requirements: 2.1
"""

from decimal import Decimal

from marshmallow import Schema, ValidationError, fields, validate, validates


class FeeTypeCreateSchema(Schema):
    """Validate the body of POST /api/v1/fee-types."""

    # Required fields
    name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    amount = fields.Decimal(
        required=True,
        places=2,
        as_string=False,
    )
    due_date = fields.Date(
        required=True,
        format="iso",  # expects YYYY-MM-DD
    )

    # Optional fields
    description = fields.String(
        load_default=None,
        allow_none=True,
    )
    currency = fields.String(
        load_default="USD",
        validate=validate.Length(min=1, max=10),
    )
    is_active = fields.Boolean(load_default=True)

    @validates("amount")
    def validate_amount(self, value: Decimal) -> Decimal:
        """Ensure amount is strictly greater than zero."""
        if value <= 0:
            raise ValidationError("amount must be greater than 0.")
        return value


class FeeTypeUpdateSchema(Schema):
    """Validate the body of PUT /api/v1/fee-types/:id.

    All fields are optional; only those present will be updated.
    """

    name = fields.String(
        validate=validate.Length(min=1, max=100),
    )
    description = fields.String(allow_none=True)
    amount = fields.Decimal(
        places=2,
        as_string=False,
    )
    currency = fields.String(
        validate=validate.Length(min=1, max=10),
    )
    due_date = fields.Date(format="iso")
    is_active = fields.Boolean()

    @validates("amount")
    def validate_amount(self, value: Decimal) -> Decimal:
        """Ensure amount is strictly greater than zero."""
        if value <= 0:
            raise ValidationError("amount must be greater than 0.")
        return value
