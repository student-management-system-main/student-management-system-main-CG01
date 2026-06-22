"""
Transaction recording and reversal blueprint.

Endpoints
---------
GET  /api/v1/transactions            — list transactions with filters (viewer+)
POST /api/v1/transactions            — record a payment transaction (admin only)
POST /api/v1/transactions/:id/reverse — create a reversal transaction (admin only)

Immutability is enforced by providing no PUT or DELETE routes on this
blueprint and by returning 405 Method Not Allowed for any such attempt.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import random
import string
from datetime import date, datetime, timezone

from marshmallow import ValidationError
from flask import Blueprint, jsonify, request
from sqlalchemy import and_

from app import db
from app.audit.helpers import write_audit_log
from app.auth.decorators import admin_required, get_current_user_id, viewer_or_admin_required
from app.models.invoice import Invoice
from app.models.student import Student
from app.models.transaction import Transaction
from app.transactions.schemas import TransactionCreateSchema

transactions_bp = Blueprint("transactions", __name__)

_create_schema = TransactionCreateSchema()


# ---------------------------------------------------------------------------
# Helper: serialise a Transaction to dict
# ---------------------------------------------------------------------------

def _transaction_to_dict(txn: Transaction) -> dict:
    """Serialize a Transaction ORM object to a plain dict for JSON responses."""
    return {
        "id": txn.id,
        "transaction_ref": txn.transaction_ref,
        "student_id": txn.student_id,
        "invoice_id": txn.invoice_id,
        # Decimal serialized as string to preserve precision (Req 3.1)
        "amount": str(txn.amount),
        "payment_method": txn.payment_method,
        "type": txn.type,
        "reversal_of": txn.reversal_of,
        "created_at": txn.created_at.isoformat() if txn.created_at else None,
    }


def _generate_transaction_ref() -> str:
    """
    Generate a unique transaction reference in the format TXN-YYYYMMDD-NNNNNN
    where NNNNNN is 6 random digits.
    """
    today = date.today().strftime("%Y%m%d")
    digits = "".join(random.choices(string.digits, k=6))
    return f"TXN-{today}-{digits}"


def _determine_invoice_status(invoice: Invoice) -> str:
    """
    Determine the correct invoice status after a reversal restores the balance.
    Returns 'overdue' if the due_date has passed, otherwise 'unpaid'.
    """
    today = date.today()
    if invoice.due_date and invoice.due_date < today:
        return "overdue"
    return "unpaid"


# ---------------------------------------------------------------------------
# Immutability guard — block PUT / DELETE on the transactions collection
# ---------------------------------------------------------------------------

@transactions_bp.route("/", methods=["PUT", "DELETE"])
@transactions_bp.route("/<int:transaction_id>", methods=["PUT", "DELETE"])
def transactions_immutable(**kwargs):
    """
    Transactions are immutable records.  PUT and DELETE are not permitted.
    Returns 405 Method Not Allowed (Requirement 3.5).
    """
    return (
        jsonify(
            {
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": (
                        "Transactions are immutable. "
                        "They cannot be modified or deleted. "
                        "Use POST /transactions/:id/reverse to reverse a transaction."
                    ),
                    "details": {},
                }
            }
        ),
        405,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/transactions
# ---------------------------------------------------------------------------

@transactions_bp.route("/", methods=["GET"])
@viewer_or_admin_required
def list_transactions():
    """
    Return a paginated list of transactions with optional filters.

    Query parameters
    ----------------
    student_id  : int   — filter by student
    invoice_id  : int   — filter by invoice
    date_from   : str   — ISO date (YYYY-MM-DD), inclusive lower bound on created_at
    date_to     : str   — ISO date (YYYY-MM-DD), inclusive upper bound on created_at
    page        : int   — page number (default 1)
    per_page    : int   — results per page (default 20, max 100)

    Requirements: 3.1
    """
    # --- parse query params ---
    errors = {}

    student_id = request.args.get("student_id")
    if student_id is not None:
        try:
            student_id = int(student_id)
        except ValueError:
            errors["student_id"] = "Must be an integer."

    invoice_id = request.args.get("invoice_id")
    if invoice_id is not None:
        try:
            invoice_id = int(invoice_id)
        except ValueError:
            errors["invoice_id"] = "Must be an integer."

    date_from_str = request.args.get("date_from")
    date_from = None
    if date_from_str:
        try:
            date_from = datetime.fromisoformat(date_from_str)
        except ValueError:
            errors["date_from"] = "Must be a valid ISO date (YYYY-MM-DD)."

    date_to_str = request.args.get("date_to")
    date_to = None
    if date_to_str:
        try:
            # Include the full day by using end-of-day
            dt = datetime.fromisoformat(date_to_str)
            date_to = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        except ValueError:
            errors["date_to"] = "Must be a valid ISO date (YYYY-MM-DD)."

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            errors["page"] = "Must be >= 1."
    except ValueError:
        errors["page"] = "Must be an integer."
        page = 1

    try:
        per_page = int(request.args.get("per_page", 20))
        if per_page < 1:
            errors["per_page"] = "Must be >= 1."
        elif per_page > 100:
            per_page = 100
    except ValueError:
        errors["per_page"] = "Must be an integer."
        per_page = 20

    if errors:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed.",
                        "details": errors,
                    }
                }
            ),
            400,
        )

    # --- build query ---
    filters = []
    if student_id is not None:
        filters.append(Transaction.student_id == student_id)
    if invoice_id is not None:
        filters.append(Transaction.invoice_id == invoice_id)
    if date_from is not None:
        filters.append(Transaction.created_at >= date_from)
    if date_to is not None:
        filters.append(Transaction.created_at <= date_to)

    query = Transaction.query
    if filters:
        query = query.filter(and_(*filters))

    query = query.order_by(Transaction.created_at.desc())
    total = query.count()
    transactions = query.offset((page - 1) * per_page).limit(per_page).all()

    return (
        jsonify(
            {
                "data": {
                    "transactions": [_transaction_to_dict(t) for t in transactions],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/transactions
# ---------------------------------------------------------------------------

@transactions_bp.route("/", methods=["POST"])
@admin_required
def create_transaction():
    """
    Record a payment transaction against an invoice.

    Business rules
    --------------
    - amount must be > 0  (Requirement 3.3)
    - amount must be ≤ invoice.outstanding_balance  (Requirement 3.4)
    - The invoice row is locked with FOR UPDATE to prevent concurrent balance
      drift (SERIALIZABLE-equivalent protection)  (Requirement 3.1)
    - INSERT transaction + UPDATE invoice balance happen atomically
    - If outstanding_balance reaches 0 → set invoice.status = 'paid' and
      record invoice.paid_at  (Requirement 2.6)
    - Write an audit log entry  (Requirement 9.1)
    - Enqueue risk_score_task after commit  (Requirement 4.2)
    - Return 201 within 2 s  (Requirement 3.2)

    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    json_data = request.get_json(silent=True) or {}

    # --- schema validation ---
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

    amount = data["amount"]
    student_id = data["student_id"]
    invoice_id = data["invoice_id"]
    payment_method = data["payment_method"]

    # --- amount > 0 (belt-and-suspenders, schema already checks this) ---
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

    # --- validate student exists ---
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

    # --- lock the invoice row to prevent concurrent balance updates ---
    invoice = (
        db.session.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .with_for_update()
        .first()
    )
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

    # --- validate invoice belongs to the provided student ---
    if invoice.student_id != student_id:
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invoice does not belong to the specified student.",
                        "details": {},
                    }
                }
            ),
            422,
        )

    # --- validate invoice is payable ---
    if invoice.status in ("paid", "cancelled"):
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Invoice is already {invoice.status} and cannot accept payments.",
                        "details": {"invoice_status": invoice.status},
                    }
                }
            ),
            422,
        )

    # --- validate amount ≤ outstanding balance (Requirement 3.4) ---
    if amount > invoice.outstanding_balance:
        return (
            jsonify(
                {
                    "error": {
                        "code": "PAYMENT_EXCEEDS_BALANCE",
                        "message": (
                            f"Payment amount {amount} exceeds the outstanding balance "
                            f"{invoice.outstanding_balance}."
                        ),
                        "details": {
                            "amount": str(amount),
                            "outstanding_balance": str(invoice.outstanding_balance),
                        },
                    }
                }
            ),
            422,
        )

    # --- generate unique transaction ref ---
    # Retry up to 10 times to avoid (unlikely) collision on the same day
    for _ in range(10):
        ref = _generate_transaction_ref()
        existing = Transaction.query.filter_by(transaction_ref=ref).first()
        if existing is None:
            break

    # --- snapshot invoice state for audit ---
    prev_balance = invoice.outstanding_balance
    prev_status = invoice.status

    # --- create the transaction record (INSERT only) ---
    txn = Transaction(
        transaction_ref=ref,
        student_id=student_id,
        invoice_id=invoice_id,
        amount=amount,
        payment_method=payment_method,
        type="payment",
        reversal_of=None,
    )
    db.session.add(txn)

    # --- update invoice outstanding balance atomically ---
    new_balance = invoice.outstanding_balance - amount
    invoice.outstanding_balance = new_balance

    # --- if fully paid, update status and paid_at (Requirement 2.6) ---
    if new_balance == 0:
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

    # --- write audit log ---
    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="transaction",
        resource_id=None,  # Not yet committed; will be set after flush
        action="create",
        previous_values=None,
        new_values={
            "transaction_ref": ref,
            "student_id": student_id,
            "invoice_id": invoice_id,
            "amount": str(amount),
            "payment_method": payment_method,
            "invoice_balance_before": str(prev_balance),
            "invoice_balance_after": str(new_balance),
            "invoice_status_before": prev_status,
            "invoice_status_after": invoice.status,
        },
    )

    # --- commit everything atomically ---
    db.session.commit()

    # --- enqueue risk score recomputation after commit (Requirement 4.2) ---
    try:
        from app.risk.tasks import risk_score_task  # noqa: PLC0415
        risk_score_task.delay(student_id)
    except Exception as exc:  # noqa: BLE001
        # Non-blocking — task queue failure must not fail the payment request
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "create_transaction: could not enqueue risk_score_task for student %s: %s",
            student_id,
            exc,
        )

    return jsonify({"data": _transaction_to_dict(txn)}), 201


# ---------------------------------------------------------------------------
# POST /api/v1/transactions/:id/reverse
# ---------------------------------------------------------------------------

@transactions_bp.route("/<int:transaction_id>/reverse", methods=["POST"])
@admin_required
def reverse_transaction(transaction_id: int):
    """
    Create a reversal transaction that cancels a prior payment.

    Business rules
    --------------
    - Only 'payment' type transactions can be reversed  (Requirement 3.5)
    - A reversal re-uses the original's payment_method and amount
    - Restores invoice.outstanding_balance += original.amount
    - If the invoice was 'paid' at reversal time, revert to 'unpaid' or
      'overdue' based on due_date  (Requirement 3.6)
    - Writes an audit log entry  (Requirement 9.1)
    - Returns 201 with the reversal transaction dict

    Requirements: 3.5, 3.6
    """
    # --- load original transaction ---
    original = db.session.get(Transaction, transaction_id)
    if original is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Transaction {transaction_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    # --- only payment transactions can be reversed ---
    if original.type != "payment":
        return (
            jsonify(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Only payment transactions can be reversed.",
                        "details": {"transaction_type": original.type},
                    }
                }
            ),
            422,
        )

    # --- prevent double-reversal ---
    existing_reversal = (
        Transaction.query.filter_by(reversal_of=transaction_id).first()
    )
    if existing_reversal is not None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "ALREADY_REVERSED",
                        "message": (
                            f"Transaction {transaction_id} has already been reversed "
                            f"(reversal transaction id={existing_reversal.id})."
                        ),
                        "details": {"reversal_transaction_id": existing_reversal.id},
                    }
                }
            ),
            409,
        )

    # --- lock the invoice row to prevent concurrent balance updates ---
    invoice = (
        db.session.query(Invoice)
        .filter(Invoice.id == original.invoice_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Invoice {original.invoice_id} not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    # --- snapshot for audit ---
    prev_balance = invoice.outstanding_balance
    prev_status = invoice.status

    # --- generate unique transaction ref ---
    for _ in range(10):
        ref = _generate_transaction_ref()
        existing = Transaction.query.filter_by(transaction_ref=ref).first()
        if existing is None:
            break

    # --- create reversal transaction ---
    reversal = Transaction(
        transaction_ref=ref,
        student_id=original.student_id,
        invoice_id=original.invoice_id,
        amount=original.amount,
        payment_method=original.payment_method,
        type="reversal",
        reversal_of=original.id,
    )
    db.session.add(reversal)

    # --- restore invoice outstanding balance ---
    new_balance = invoice.outstanding_balance + original.amount
    invoice.outstanding_balance = new_balance

    # --- if invoice was paid, revert to appropriate status (Requirement 3.6) ---
    if prev_status == "paid":
        invoice.status = _determine_invoice_status(invoice)
        invoice.paid_at = None

    # --- write audit log ---
    actor_id = get_current_user_id()
    write_audit_log(
        actor_id=actor_id,
        resource_type="transaction",
        resource_id=original.id,
        action="reverse",
        previous_values={
            "invoice_balance": str(prev_balance),
            "invoice_status": prev_status,
        },
        new_values={
            "reversal_transaction_ref": ref,
            "original_transaction_id": original.id,
            "original_amount": str(original.amount),
            "invoice_balance_after": str(new_balance),
            "invoice_status_after": invoice.status,
        },
    )

    # --- commit atomically ---
    db.session.commit()

    # --- enqueue risk score recomputation after commit ---
    try:
        from app.risk.tasks import risk_score_task  # noqa: PLC0415
        risk_score_task.delay(original.student_id)
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "reverse_transaction: could not enqueue risk_score_task for student %s: %s",
            original.student_id,
            exc,
        )

    return jsonify({"data": _transaction_to_dict(reversal)}), 201
