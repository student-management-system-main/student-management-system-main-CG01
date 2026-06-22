"""
Transaction ORM model.

Represents an immutable payment or reversal event.  Once recorded, a
transaction MUST NOT be modified or deleted — reversals are handled by
creating a new Transaction with type='reversal' that references the
original via `reversal_of`.
"""

from sqlalchemy import DateTime, Enum, Index, Integer, Numeric, String, func

from app import db


class Transaction(db.Model):
    """An immutable payment or reversal record."""

    __tablename__ = "transactions"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    transaction_ref = db.Column(String(80), unique=True, nullable=False)
    student_id = db.Column(
        Integer,
        db.ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id = db.Column(
        Integer,
        db.ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = db.Column(Numeric(12, 2), nullable=False)
    payment_method = db.Column(String(50), nullable=False)
    type = db.Column(
        Enum("payment", "reversal", name="transaction_type_enum"),
        nullable=False,
        default="payment",
        server_default="payment",
    )
    # Self-referential FK: reversal transactions point back to the original
    reversal_of = db.Column(
        Integer,
        db.ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Immutable record — no updated_at column
    created_at = db.Column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_transaction_student", "student_id"),
        Index("idx_transaction_invoice", "invoice_id"),
    )

    # Relationships
    student = db.relationship(
        "Student",
        back_populates="transactions",
        foreign_keys=[student_id],
    )
    invoice = db.relationship(
        "Invoice",
        back_populates="transactions",
        foreign_keys=[invoice_id],
    )
    # Self-referential: the original transaction that this one reverses
    original_transaction = db.relationship(
        "Transaction",
        remote_side=[id],
        foreign_keys=[reversal_of],
        backref=db.backref("reversals", lazy="dynamic"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} ref={self.transaction_ref!r} "
            f"type={self.type!r} amount={self.amount}>"
        )
