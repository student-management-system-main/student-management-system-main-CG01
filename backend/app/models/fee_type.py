"""
FeeType ORM model.

Represents a named fee category (e.g., tuition, library, lab) with a fixed
amount, currency, and due date.
"""

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func

from app import db


class FeeType(db.Model):
    """A named fee category with a fixed amount and due date."""

    __tablename__ = "fee_types"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(100), nullable=False)
    description = db.Column(Text, nullable=True)
    amount = db.Column(Numeric(12, 2), nullable=False)
    currency = db.Column(
        String(10), nullable=False, default="USD", server_default="USD"
    )
    due_date = db.Column(Date, nullable=False)
    is_active = db.Column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at = db.Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    invoice_line_items = db.relationship(
        "InvoiceLineItem",
        back_populates="fee_type",
        foreign_keys="InvoiceLineItem.fee_type_id",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return (
            f"<FeeType id={self.id} name={self.name!r} "
            f"amount={self.amount} currency={self.currency!r}>"
        )
