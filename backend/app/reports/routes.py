"""
Reports blueprint routes.

Endpoints
---------
POST /api/v1/reports              — generate a report with optional filters
GET  /api/v1/reports/:id/export   — export a previously generated report (CSV or PDF)

Reports are generated on demand and cached in memory for 1 hour.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from marshmallow import ValidationError
from flask import Blueprint, Response, jsonify, request
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from app import db
from app.audit.helpers import write_audit_log
from app.auth.decorators import get_current_user_id, viewer_or_admin_required
from app.models.fee_type import FeeType
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.risk_score import RiskScore
from app.models.student import Student
from app.models.transaction import Transaction
from app.reports.schemas import ReportRequestSchema

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__)

# ---------------------------------------------------------------------------
# In-memory report cache: {report_id: {"data": ..., "expires_at": datetime}}
# ---------------------------------------------------------------------------
_report_cache: dict[str, dict] = {}

# Cache TTL: 1 hour
_CACHE_TTL = timedelta(hours=1)

_request_schema = ReportRequestSchema()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _store_report(report_id: str, report_data: dict) -> None:
    """Store a generated report in the in-memory cache with a TTL."""
    _report_cache[report_id] = {
        "data": report_data,
        "expires_at": datetime.now(timezone.utc) + _CACHE_TTL,
    }


def _get_report(report_id: str) -> dict | None:
    """
    Retrieve a cached report by ID.

    Returns ``None`` if the report is not found or has expired.
    Expired entries are evicted lazily on access.
    """
    entry = _report_cache.get(report_id)
    if entry is None:
        return None
    if datetime.now(timezone.utc) > entry["expires_at"]:
        del _report_cache[report_id]
        return None
    return entry["data"]


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------

def _build_fee_collection_records(filters: dict) -> list[dict]:
    """
    Build the fee_collection report.

    Returns one record per invoice joined with student info and fee totals.

    Filters applied (all optional):
      - date_from / date_to   → invoice.created_at range
      - student_group         → invoice.student_id IN (...)
      - fee_type              → invoice has a line item for these fee_type_ids
      - invoice_status        → invoice.status
      - risk_category         → student's latest risk_score.risk_category
    """
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    student_group = filters.get("student_group")
    fee_type_filter = filters.get("fee_type")
    invoice_status = filters.get("invoice_status")
    risk_category = filters.get("risk_category")

    query = db.session.query(Invoice).join(Student, Invoice.student_id == Student.id)

    if date_from is not None:
        query = query.filter(Invoice.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        # include the full day
        query = query.filter(Invoice.created_at <= datetime.combine(date_to, datetime.max.time()))
    if student_group:
        query = query.filter(Invoice.student_id.in_(student_group))
    if invoice_status:
        query = query.filter(Invoice.status == invoice_status)
    if fee_type_filter:
        # Only invoices that have at least one line item matching the fee types
        query = query.join(InvoiceLineItem, Invoice.id == InvoiceLineItem.invoice_id).filter(
            InvoiceLineItem.fee_type_id.in_(fee_type_filter)
        ).distinct()
    if risk_category:
        # Join against the latest risk score for each student
        latest_risk_subquery = (
            db.session.query(
                RiskScore.student_id,
                db.func.max(RiskScore.computed_at).label("latest_computed_at"),
            )
            .group_by(RiskScore.student_id)
            .subquery()
        )
        query = (
            query
            .join(
                latest_risk_subquery,
                Invoice.student_id == latest_risk_subquery.c.student_id,
            )
            .join(
                RiskScore,
                (RiskScore.student_id == latest_risk_subquery.c.student_id)
                & (RiskScore.computed_at == latest_risk_subquery.c.latest_computed_at),
            )
            .filter(RiskScore.risk_category == risk_category)
        )

    invoices = query.all()

    records = []
    for inv in invoices:
        student = inv.student

        # Compute total paid = sum of payment transactions
        total_paid = (
            db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
            .filter(
                Transaction.invoice_id == inv.id,
                Transaction.type == "payment",
            )
            .scalar()
        )
        # Subtract reversals
        total_reversed = (
            db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0))
            .filter(
                Transaction.invoice_id == inv.id,
                Transaction.type == "reversal",
            )
            .scalar()
        )
        net_paid = Decimal(str(total_paid)) - Decimal(str(total_reversed))

        # Count overdue invoices for this student
        overdue_count = (
            Invoice.query
            .filter(Invoice.student_id == student.id, Invoice.status == "overdue")
            .count()
        )

        records.append(
            {
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_status": inv.status,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "total_amount": str(inv.total_amount),
                "outstanding_balance": str(inv.outstanding_balance),
                "net_paid": str(net_paid),
                "student_id": student.id,
                "student_number": student.student_number,
                "student_name": f"{student.first_name} {student.last_name}",
                "student_email": student.email,
                "overdue_invoice_count": overdue_count,
            }
        )

    return records


def _build_high_risk_students_records(filters: dict) -> list[dict]:
    """
    Build the high_risk_students report.

    Returns one record per student whose latest risk category is 'high'.

    Filters applied (all optional):
      - date_from / date_to   → risk_score.computed_at range for the latest score
      - student_group         → student.id IN (...)
    """
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    student_group = filters.get("student_group")

    # Subquery: latest computed_at per student
    latest_risk_subquery = (
        db.session.query(
            RiskScore.student_id,
            db.func.max(RiskScore.computed_at).label("latest_computed_at"),
        )
        .group_by(RiskScore.student_id)
        .subquery()
    )

    query = (
        db.session.query(Student, RiskScore)
        .join(
            latest_risk_subquery,
            Student.id == latest_risk_subquery.c.student_id,
        )
        .join(
            RiskScore,
            (RiskScore.student_id == latest_risk_subquery.c.student_id)
            & (RiskScore.computed_at == latest_risk_subquery.c.latest_computed_at),
        )
        .filter(RiskScore.risk_category == "high")
    )

    if student_group:
        query = query.filter(Student.id.in_(student_group))
    if date_from is not None:
        query = query.filter(RiskScore.computed_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.filter(RiskScore.computed_at <= datetime.combine(date_to, datetime.max.time()))

    rows = query.all()

    records = []
    for student, risk_score in rows:
        # Total outstanding balance = sum of all non-cancelled invoice outstanding balances
        total_outstanding = (
            db.session.query(
                db.func.coalesce(db.func.sum(Invoice.outstanding_balance), 0)
            )
            .filter(
                Invoice.student_id == student.id,
                Invoice.status.in_(["unpaid", "overdue"]),
            )
            .scalar()
        )

        # Last payment date = latest transaction created_at for this student
        last_payment = (
            db.session.query(db.func.max(Transaction.created_at))
            .filter(
                Transaction.student_id == student.id,
                Transaction.type == "payment",
            )
            .scalar()
        )

        records.append(
            {
                "student_id": student.id,
                "student_number": student.student_number,
                "student_name": f"{student.first_name} {student.last_name}",
                "student_email": student.email,
                "student_status": student.status,
                "risk_score": str(risk_score.score),
                "risk_category": risk_score.risk_category,
                "risk_computed_at": risk_score.computed_at.isoformat() if risk_score.computed_at else None,
                "total_outstanding_balance": str(total_outstanding),
                "last_payment_date": last_payment.isoformat() if last_payment else None,
            }
        )

    return records


# ---------------------------------------------------------------------------
# PDF generation helper
# ---------------------------------------------------------------------------

def _generate_pdf(report_data: dict) -> bytes:
    """
    Generate a PDF document from a cached report data dict.

    Builds a ReportLab ``SimpleDocTemplate`` with:
    - Institution name header (hardcoded "Fee Management System")
    - Generation timestamp, applied filters, and admin identifier
    - Tabular data using ``TableStyle``

    Parameters
    ----------
    report_data:
        The dict stored in the in-memory cache by ``generate_report``.

    Returns
    -------
    bytes
        Raw PDF bytes suitable for streaming in a Flask ``Response``.

    Requirements: 7.3, 7.4
    """
    records: list[dict] = report_data.get("records", [])
    report_type: str = report_data.get("report_type", "report")
    generated_at: str = report_data.get("generated_at", "")
    filters: dict = report_data.get("filters", {})
    generated_by = report_data.get("generated_by", "N/A")
    report_id: str = report_data.get("report_id", "")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=4,
    )

    story = []

    # --- Header section ---
    story.append(Paragraph("Fee Management System", title_style))
    story.append(Paragraph(f"Report Type: {report_type.replace('_', ' ').title()}", meta_style))
    story.append(Paragraph(f"Report ID: {report_id}", meta_style))
    story.append(Paragraph(f"Generated At: {generated_at}", meta_style))
    story.append(Paragraph(f"Generated By (user_id): {generated_by}", meta_style))

    # Render filters as a readable string
    if filters:
        filter_parts = [f"{k}={v}" for k, v in filters.items() if v is not None]
        filters_str = ", ".join(filter_parts) if filter_parts else "None"
    else:
        filters_str = "None"
    story.append(Paragraph(f"Applied Filters: {filters_str}", meta_style))
    story.append(Spacer(1, 0.5 * cm))

    # --- Data table ---
    if records:
        column_headers = list(records[0].keys())

        # Build table data: header row + data rows
        table_data = [column_headers]
        for record in records:
            row = [str(record.get(col, "")) for col in column_headers]
            table_data.append(row)

        # Auto-size columns to fit page width
        page_width = landscape(A4)[0] - 3 * cm  # subtract margins
        col_width = page_width / len(column_headers)
        col_widths = [col_width] * len(column_headers)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    # Header row styling
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    # Data rows
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                    ("TOPPADDING", (0, 1), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                    # Alternating row background
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                    # Grid
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#1D4ED8")),
                    # Overflow handling
                    ("WORDWRAP", (0, 0), (-1, -1), True),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No records matched the applied filters.", meta_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# POST /api/v1/reports
# ---------------------------------------------------------------------------

@reports_bp.route("/", methods=["POST"])
@viewer_or_admin_required
def generate_report():
    """
    Generate a report based on the provided filters.

    Accepts JSON with optional filter fields; see ``ReportRequestSchema``.
    Stores the report in the in-memory cache and returns a report_id that can
    be used to export via ``GET /api/v1/reports/:id/export``.

    Report types
    ------------
    fee_collection      — invoice data with student info, fee totals, overdue counts
    high_risk_students  — students with risk_category='high', outstanding balances,
                          last payment date

    Requirements: 7.1, 7.2, 7.5, 7.6
    """
    json_data = request.get_json(silent=True) or {}

    try:
        filters = _request_schema.load(json_data)
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

    report_type: str = filters.get("report_type", "fee_collection")
    actor_id = get_current_user_id()
    report_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc)

    # Build the serialisable filters dict (dates → ISO strings for JSON)
    serialisable_filters: dict = {}
    for key, value in filters.items():
        if value is None:
            continue
        if hasattr(value, "isoformat"):
            serialisable_filters[key] = value.isoformat()
        else:
            serialisable_filters[key] = value

    # Generate report records
    try:
        if report_type == "fee_collection":
            records = _build_fee_collection_records(filters)
        elif report_type == "high_risk_students":
            records = _build_high_risk_students_records(filters)
        else:
            # Should be unreachable (schema validates report_type), but defensive
            return (
                jsonify(
                    {
                        "error": {
                            "code": "BAD_REQUEST",
                            "message": f"Unknown report_type: {report_type!r}",
                            "details": {},
                        }
                    }
                ),
                400,
            )
    except Exception as exc:
        logger.exception("Report generation failed: %s", exc)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Report generation failed. Please try again.",
                        "details": {},
                    }
                }
            ),
            500,
        )

    report_data = {
        "report_id": report_id,
        "report_type": report_type,
        "filters": serialisable_filters,
        "records": records,
        "total": len(records),
        "generated_at": generated_at.isoformat(),
        "generated_by": actor_id,
    }

    # Store in cache for export
    _store_report(report_id, report_data)

    # Write audit log entry (Requirement 7.6, 9.1)
    try:
        write_audit_log(
            actor_id=actor_id,
            resource_type="report",
            resource_id=None,
            action="report_generate",
            previous_values=None,
            new_values={
                "report_id": report_id,
                "report_type": report_type,
                "filters": serialisable_filters,
                "total_records": len(records),
            },
        )
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write audit log for report %s: %s", report_id, exc)
        db.session.rollback()

    return jsonify({"data": report_data}), 200


# ---------------------------------------------------------------------------
# GET /api/v1/reports/:id/export
# ---------------------------------------------------------------------------

@reports_bp.route("/<string:report_id>/export", methods=["GET"])
@viewer_or_admin_required
def export_report(report_id: str):
    """
    Export a previously generated report.

    Query parameters
    ----------------
    format : csv | pdf (default csv)

    The report must exist in the in-memory cache (populated by ``POST /api/v1/reports``).
    Reports expire after 1 hour.

    Returns
    -------
    - CSV: streamed response with ``Content-Disposition: attachment`` header
    - PDF: PDF document generated with ReportLab, returned as ``application/pdf``
    - 404 if report_id not found or expired

    Requirements: 7.3, 7.4
    """
    export_format = request.args.get("format", "csv").lower()

    if export_format not in ("csv", "pdf"):
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "format must be 'csv' or 'pdf'.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    report_data = _get_report(report_id)
    if report_data is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Report '{report_id}' not found or has expired.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    if export_format == "pdf":
        # --- PDF export ---
        actor_id = get_current_user_id()
        records: list[dict] = report_data.get("records", [])
        report_type: str = report_data.get("report_type", "report")
        generated_at: str = report_data.get("generated_at", "")
        filters: dict = report_data.get("filters", {})
        generated_by: int = report_data.get("generated_by", actor_id)

        try:
            pdf_bytes = _generate_pdf(report_data)
        except Exception as exc:
            logger.exception("PDF generation failed for report %s: %s", report_id, exc)
            return (
                jsonify(
                    {
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "PDF generation failed. Please try again.",
                            "details": {},
                        }
                    }
                ),
                500,
            )

        # Write audit log entry
        try:
            write_audit_log(
                actor_id=actor_id,
                resource_type="report",
                resource_id=None,
                action="report_export",
                previous_values=None,
                new_values={
                    "report_id": report_id,
                    "report_type": report_type,
                    "format": "pdf",
                    "total_records": len(records),
                },
            )
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to write audit log for report export %s: %s", report_id, exc)
            db.session.rollback()

        filename = f"report_{report_type}_{report_id[:8]}.pdf"
        return Response(
            pdf_bytes,
            status=200,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # --- CSV export ---
    actor_id = get_current_user_id()
    records: list[dict] = report_data.get("records", [])
    report_type: str = report_data.get("report_type", "report")
    generated_at: str = report_data.get("generated_at", "")
    filters: dict = report_data.get("filters", {})
    generated_by: int = report_data.get("generated_by", actor_id)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header metadata rows (Requirement 7.4)
    writer.writerow(["# Report Type", report_type])
    writer.writerow(["# Generated At", generated_at])
    writer.writerow(["# Generated By (user_id)", generated_by])
    writer.writerow(["# Report ID", report_id])
    writer.writerow(["# Filters", str(filters)])
    writer.writerow([])  # blank separator

    if records:
        # Column headers from the first record's keys
        column_headers = list(records[0].keys())
        writer.writerow(column_headers)
        for record in records:
            writer.writerow([record.get(col, "") for col in column_headers])
    else:
        writer.writerow(["# No records matched the applied filters."])

    csv_content = output.getvalue()
    output.close()

    # Write audit log entry
    try:
        write_audit_log(
            actor_id=actor_id,
            resource_type="report",
            resource_id=None,
            action="report_export",
            previous_values=None,
            new_values={
                "report_id": report_id,
                "report_type": report_type,
                "format": "csv",
                "total_records": len(records),
            },
        )
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write audit log for report export %s: %s", report_id, exc)
        db.session.rollback()

    filename = f"report_{report_type}_{report_id[:8]}.csv"
    return Response(
        csv_content,
        status=200,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
