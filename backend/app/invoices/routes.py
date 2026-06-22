"""
Invoice management blueprint.

Endpoints
---------
GET  /api/v1/invoices              — list invoices (paginated, filtered)
POST /api/v1/invoices              — create invoice with line items
GET  /api/v1/invoices/:id          — get invoice detail (includes line items)
POST /api/v1/invoices/:id/payments — apply a payment to an invoice

Requirements: 2.2, 2.3, 2.7
"""

import random
from datetime import datetime, timezone
from decimal import Decimal

from marshmallow import ValidationError
from flask import Blueprint, jsonify, request
from sqlalchemy import text

from app import db
from app.auth.decorators import admin_required, get_current_user_id, viewer_or_admin_required
from app.audit.helpers import write_audit_log
from app.models.fee_type import FeeType
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.student import Student
from app.models.transaction import Transaction
from app.invoices.schemas import InvoiceCreateSchema

invoices_bp = Blueprint("invoices", __name__)

# Reusable schema instance
_create_schema = InvoiceCreateSchema()


# ---------------------------------------------------------------------------
# Helper: serialise invoice to dict
# ---------------------------------------------------------------------------

def invoice_to_dict(invoice: Invoice, include_line_items: bool = False) -> dict:
    """Serialise an Invoice ORM object to a plain dict for JSON responses."""
    result = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "student_id": invoice.student_id,
        "total_amount": str(invoice.total_amount),
        "outstanding_balance": str(invoice.outstanding_balance),
        "status": invoice.status,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
    }
    if include_line_items:
        result["line_items"] = [
            {
                "id": item.id,
                "fee_type_id": item.fee_type_id,
                "amount": str(item.amount),
            }
            for item in invoice.line_items
        ]
    return result


# ---------------------------------------------------------------------------
# GET /api/v1/invoices
# ---------------------------------------------------------------------------

@invoices_bp.route("/", methods=["GET"])
@viewer_or_admin_required
def list_invoices():
    """
    Return a paginated list of invoices with optional filters.

    Query parameters
    ----------------
    student_id : int (optional)
    status     : unpaid | overdue | paid | cancelled (optional)
    page       : int (default 1)
    per_page   : int (default 20, max 100)

    Requirements: 2.2
    """
    # Parse query parameters
    student_id_raw = request.args.get("student_id")
    status_raw = request.args.get("status")

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except (ValueError, TypeError):
        per_page = 20

    # Validate student_id if supplied
    student_id = None
    if student_id_raw is not None:
        try:
            student_id = int(student_id_raw)
        except (ValueError, TypeError):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "BAD_REQUEST",
                            "message": "student_id must be an integer.",
                            "details": {},
                        }
                    }
                ),
                400,
            )

    # Validate status if supplied
    valid_statuses = {"unpaid", "overdue", "paid", "cancelled"}
    if status_raw is not None and status_raw not in valid_statuses:
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": f"status must be one of: {', '.join(sorted(valid_statuses))}.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # Build query
    query = Invoice.query
    if student_id is not None:
        query = query.filter(Invoice.student_id == student_id)
    if status_raw is not None:
        query = query.filter(Invoice.status == status_raw)

    total = query.count()
    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    return (
        jsonify(
            {
                "data": {
                    "invoices": [invoice_to_dict(inv) for inv in invoices],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/invoices
# ---------------------------------------------------------------------------

@invoices_bp.route("/", methods=["POST"])
@admin_required
def create_invoice():
    """
    Create a new invoice for a student, generating line items for each fee type.

    Business rules
    --------------
    - Student must be active (422 STUDENT_INACTIVE if not)
    - All fee_type_ids must exist (404 if any are missing)
    - No duplicate invoice: same student_id + same fee_type_ids + same billing_period → 409 DUPLICATE_INVOICE
    - Generates unique invoice_number: INV-{YYYYMMDD}-{student_id:05d}-{random 4 digits}
    - total_amount = sum of fee_type.amount for all fee types
    - outstanding_balance = total_amount, status = 'unpaid'

    Requirements: 2.2, 2.3, 2.7
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

    student_id: int = data["student_id"]
    fee_type_ids: list[int] = data["fee_type_ids"]
    billing_period: str = data["billing_period"]

    # Fetch student
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

    # Reject inactive students (Requirement 2.2, 1.5)
    if student.status != "active":
        return (
            jsonify(
                {
                    "error": {
                        "code": "STUDENT_INACTIVE",
                        "message": "Cannot generate an invoice for an inactive student.",
                        "details": {"student_id": student_id},
                    }
                }
            ),
            422,
        )

    # Fetch and validate all fee types
    fee_types = FeeType.query.filter(FeeType.id.in_(fee_type_ids)).all()
    found_ids = {ft.id for ft in fee_types}
    missing_ids = [fid for fid in fee_type_ids if fid not in found_ids]
    if missing_ids:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "One or more fee type IDs not found.",
                        "details": {"missing_fee_type_ids": missing_ids},
                    }
                }
            ),
            404,
        )

    # Duplicate invoice check: same student + same (sorted) fee_type_ids + same billing_period.
    # Since the Invoice model has no billing_period column, we encode the billing_period
    # into the invoice_number format:
    #   INV-{YYYYMMDD}-{YYYYMM}-{student_id:05d}-{rand4}
    # The YYYYMM segment (parts[2]) serves as a parseable billing_period tag.
    billing_period_tag = billing_period.replace("-", "")  # "2024-01" → "202401"
    sorted_fee_type_ids = sorted(fee_type_ids)

    existing_invoices = (
        Invoice.query
        .filter(Invoice.student_id == student_id)
        .all()
    )

    duplicate_found = False
    for existing in existing_invoices:
        # Extract billing_period tag from invoice_number
        # Expected format: INV-YYYYMMDD-YYYYMM-{student_id:05d}-{rand4}
        # We'll switch to this extended format below when creating.
        # For existing invoices in old format, we skip the billing_period check.
        parts = existing.invoice_number.split("-")
        if len(parts) >= 5:
            # New format: INV-YYYYMMDD-YYYYMM-00001-0000
            existing_billing_tag = parts[2]
            if existing_billing_tag == billing_period_tag:
                existing_fee_ids = sorted(item.fee_type_id for item in existing.line_items)
                if existing_fee_ids == sorted_fee_type_ids:
                    duplicate_found = True
                    break

    if duplicate_found:
        return (
            jsonify(
                {
                    "error": {
                        "code": "DUPLICATE_INVOICE",
                        "message": "An invoice already exists for this student, fee types, and billing period.",
                        "details": {
                            "student_id": student_id,
                            "fee_type_ids": sorted_fee_type_ids,
                            "billing_period": billing_period,
                        },
                    }
                }
            ),
            409,
        )

    # Generate unique invoice_number
    # Format: INV-{YYYYMMDD}-{YYYYMM}-{student_id:05d}-{rand4}
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    rand_suffix = f"{random.randint(0, 9999):04d}"
    invoice_number = f"INV-{date_str}-{billing_period_tag}-{student_id:05d}-{rand_suffix}"

    # Calculate total amount
    fee_type_map = {ft.id: ft for ft in fee_types}
    total_amount = sum(Decimal(str(fee_type_map[fid].amount)) for fid in fee_type_ids)

    # Determine due_date: use the earliest due_date among the selected fee types
    due_date = min(ft.due_date for ft in fee_types)

    # Create invoice
    invoice = Invoice(
        invoice_number=invoice_number,
        student_id=student_id,
        total_amount=total_amount,
        outstanding_balance=total_amount,
        status="unpaid",
        due_date=due_date,
    )
    db.session.add(invoice)
    db.session.flush()  # Assign invoice.id without committing

    # Create line items
    for fid in fee_type_ids:
        line_item = InvoiceLineItem(
            invoice_id=invoice.id,
            fee_type_id=fid,
            amount=Decimal(str(fee_type_map[fid].amount)),
        )
        db.session.add(line_item)

    # Write audit log
    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="invoice",
        resource_id=invoice.id,
        action="create",
        previous_values=None,
        new_values={
            "invoice_number": invoice_number,
            "student_id": student_id,
            "fee_type_ids": fee_type_ids,
            "billing_period": billing_period,
            "total_amount": str(total_amount),
            "status": "unpaid",
        },
    )

    db.session.commit()

    return jsonify({"data": invoice_to_dict(invoice, include_line_items=True)}), 201


# ---------------------------------------------------------------------------
# GET /api/v1/invoices/:id
# ---------------------------------------------------------------------------

@invoices_bp.route("/<int:invoice_id>", methods=["GET"])
@viewer_or_admin_required
def get_invoice(invoice_id: int):
    """
    Return a single invoice by ID, including its line items.

    Returns 404 if the invoice does not exist.

    Requirements: 2.2
    """
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Invoice {invoice_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    return jsonify({"data": invoice_to_dict(invoice, include_line_items=True)}), 200


# ---------------------------------------------------------------------------
# POST /api/v1/invoices/:id/payments
# ---------------------------------------------------------------------------

@invoices_bp.route("/<int:invoice_id>/payments", methods=["POST"])
@admin_required
def apply_payment(invoice_id: int):
    """
    Apply a payment to an invoice.

    Accepts JSON: {"amount": decimal, "payment_method": str}

    Business rules
    --------------
    - amount must be > 0
    - amount must be <= outstanding_balance
    - Updates outstanding_balance atomically (SERIALIZABLE transaction)
    - Creates a Transaction record
    - If outstanding_balance reaches 0: sets status='paid', paid_at=now()
    - Enqueues risk_score_task after commit

    Requirements: 2.5, 2.6, 3.1
    """
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Invoice {invoice_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    json_data = request.get_json(silent=True) or {}

    # Validate amount
    amount_raw = json_data.get("amount")
    payment_method = json_data.get("payment_method")

    if amount_raw is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "amount is required.",
                        "details": {"amount": ["Missing data for required field."]},
                    }
                }
            ),
            400,
        )

    if payment_method is None or not str(payment_method).strip():
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "payment_method is required.",
                        "details": {"payment_method": ["Missing data for required field."]},
                    }
                }
            ),
            400,
        )

    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "amount must be a valid decimal number.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    if amount <= 0:
        return (
            jsonify(
                {
                    "error": {
                        "code": "INVALID_PAYMENT_AMOUNT",
                        "message": "Payment amount must be greater than zero.",
                        "details": {"amount": str(amount)},
                    }
                }
            ),
            422,
        )

    outstanding = Decimal(str(invoice.outstanding_balance))
    if amount > outstanding:
        return (
            jsonify(
                {
                    "error": {
                        "code": "PAYMENT_EXCEEDS_BALANCE",
                        "message": "Payment amount exceeds the outstanding balance.",
                        "details": {
                            "amount": str(amount),
                            "outstanding_balance": str(outstanding),
                        },
                    }
                }
            ),
            422,
        )

    # Execute payment within a SERIALIZABLE transaction (Requirement 2.5, 3.1)
    try:
        # Set SERIALIZABLE isolation for this transaction
        db.session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        # Re-read invoice balance under lock to prevent race conditions
        invoice = (
            db.session.query(Invoice)
            .filter(Invoice.id == invoice_id)
            .with_for_update()
            .one()
        )

        outstanding_locked = Decimal(str(invoice.outstanding_balance))
        if amount > outstanding_locked:
            db.session.rollback()
            return (
                jsonify(
                    {
                        "error": {
                            "code": "PAYMENT_EXCEEDS_BALANCE",
                            "message": "Payment amount exceeds the outstanding balance.",
                            "details": {
                                "amount": str(amount),
                                "outstanding_balance": str(outstanding_locked),
                            },
                        }
                    }
                ),
                422,
            )

        previous_balance = outstanding_locked
        previous_status = invoice.status
        new_balance = outstanding_locked - amount

        # Update invoice
        invoice.outstanding_balance = new_balance

        now = datetime.now(timezone.utc)
        if new_balance == Decimal("0"):
            invoice.status = "paid"
            invoice.paid_at = now

        # Generate unique transaction reference
        rand_ref = f"{random.randint(0, 999999):06d}"
        transaction_ref = f"TXN-{now.strftime('%Y%m%d%H%M%S')}-{invoice.student_id:05d}-{rand_ref}"

        # Create Transaction record
        transaction = Transaction(
            transaction_ref=transaction_ref,
            student_id=invoice.student_id,
            invoice_id=invoice.id,
            amount=amount,
            payment_method=str(payment_method).strip(),
            type="payment",
        )
        db.session.add(transaction)

        # Write audit log
        actor_id = get_current_user_id()
        write_audit_log(
            actor_id=actor_id,
            resource_type="invoice",
            resource_id=invoice.id,
            action="payment",
            previous_values={
                "outstanding_balance": str(previous_balance),
                "status": previous_status,
            },
            new_values={
                "outstanding_balance": str(new_balance),
                "status": invoice.status,
                "amount_paid": str(amount),
                "payment_method": str(payment_method).strip(),
                "transaction_ref": transaction_ref,
            },
        )

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        raise exc

    # Enqueue risk score recomputation after commit (Requirement 4.2)
    try:
        from app.risk.tasks import risk_score_task  # noqa: PLC0415
        risk_score_task.delay(invoice.student_id)
    except Exception as enqueue_exc:  # noqa: BLE001
        # Log but do not fail the request if Celery is unavailable
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "apply_payment: could not enqueue risk_score_task for student %s: %s",
            invoice.student_id,
            enqueue_exc,
        )

    # Suppress scheduled reminders when invoice transitions to paid (Requirement 5.7)
    if invoice.status == "paid":
        try:
            from app.notifications.tasks import suppress_reminders  # noqa: PLC0415
            suppress_reminders.delay(invoice.id)
        except Exception as enqueue_exc:  # noqa: BLE001
            import logging  # noqa: PLC0415
            logging.getLogger(__name__).warning(
                "apply_payment: could not enqueue suppress_reminders for invoice %s: %s",
                invoice.id,
                enqueue_exc,
            )

    return jsonify({"data": invoice_to_dict(invoice, include_line_items=True)}), 200
