"""
Invoice ORM model.

Represents a billing document issued to a student, tracking the total amount
owed, outstanding balance, and payment status.
"""

from sqlalchemy import Date, DateTime, Enum, Index, Integer, Numeric, String, func

from app import db


class Invoice(db.Model):
    """A billing document linking a student to one or more fee types."""

    __tablename__ = "invoices"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = db.Column(String(50), unique=True, nullable=False)
    student_id = db.Column(
        Integer,
        db.ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
    )
    total_amount = db.Column(Numeric(12, 2), nullable=False)
    outstanding_balance = db.Column(Numeric(12, 2), nullable=False)
    status = db.Column(
        Enum("unpaid", "overdue", "paid", "cancelled", name="invoice_status_enum"),
        nullable=False,
        default="unpaid",
        server_default="unpaid",
    )
    due_date = db.Column(Date, nullable=False)
    paid_at = db.Column(DateTime, nullable=True)
    created_at = db.Column(DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes
    __table_args__ = (
        Index("idx_invoice_student", "student_id"),
        Index("idx_invoice_status", "status"),
        Index("idx_invoice_due_date", "due_date"),
    )

    # Relationships
    student = db.relationship(
        "Student",
        back_populates="invoices",
        foreign_keys=[student_id],
    )
    line_items = db.relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        foreign_keys="InvoiceLineItem.invoice_id",
        cascade="all, delete-orphan",
        lazy="select",
    )
    transactions = db.relationship(
        "Transaction",
        back_populates="invoice",
        foreign_keys="Transaction.invoice_id",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice id={self.id} number={self.invoice_number!r} "
            f"status={self.status!r} balance={self.outstanding_balance}>"
        )
