"""
models package — barrel export of all ORM models.

Import from here to ensure all models are registered with SQLAlchemy's
metadata before `db.create_all()` or Alembic migrations are run.

Usage:
    from app.models import User, Student, FeeType, Invoice, InvoiceLineItem
    from app.models import Transaction, RiskScore, Log
"""

from app.models.user import User
from app.models.student import Student
from app.models.fee_type import FeeType
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.transaction import Transaction
from app.models.risk_score import RiskScore
from app.models.log import Log

__all__ = [
    "User",
    "Student",
    "FeeType",
    "Invoice",
    "InvoiceLineItem",
    "Transaction",
    "RiskScore",
    "Log",
]
