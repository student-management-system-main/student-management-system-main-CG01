"""
Marshmallow schemas for report request validation.

``ReportRequestSchema`` — validates the POST /api/v1/reports payload.

Requirements: 7.1, 7.2
"""

from marshmallow import Schema, fields, validate


class ReportRequestSchema(Schema):
    """Validate the body of POST /api/v1/reports."""

    # Optional date range filters (ISO date strings YYYY-MM-DD)
    date_from = fields.Date(
        load_default=None,
        allow_none=True,
        format="iso",
        metadata={"description": "Filter records from this date (inclusive)."},
    )
    date_to = fields.Date(
        load_default=None,
        allow_none=True,
        format="iso",
        metadata={"description": "Filter records up to this date (inclusive)."},
    )

    # Optional list of student IDs to scope the report
    student_group = fields.List(
        fields.Integer(),
        load_default=None,
        allow_none=True,
        metadata={"description": "Limit report to these student IDs."},
    )

    # Optional list of fee type IDs to filter by
    fee_type = fields.List(
        fields.Integer(),
        load_default=None,
        allow_none=True,
        metadata={"description": "Limit report to invoices that include these fee type IDs."},
    )

    # Optional invoice status filter
    invoice_status = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(
            ["unpaid", "overdue", "paid", "cancelled"],
            error="invoice_status must be one of: unpaid, overdue, paid, cancelled.",
        ),
        metadata={"description": "Filter invoices by status."},
    )

    # Optional risk category filter
    risk_category = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(
            ["low", "medium", "high"],
            error="risk_category must be one of: low, medium, high.",
        ),
        metadata={"description": "Filter students by current risk category."},
    )

    # Report type — determines what SQL queries and output structure to use
    report_type = fields.String(
        load_default="fee_collection",
        validate=validate.OneOf(
            ["fee_collection", "high_risk_students"],
            error="report_type must be one of: fee_collection, high_risk_students.",
        ),
        metadata={"description": "Type of report to generate."},
    )
