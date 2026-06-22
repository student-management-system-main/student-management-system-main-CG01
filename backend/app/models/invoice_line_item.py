"""
InvoiceLineItem ORM model.

Represents a single fee-type entry within an invoice, capturing the amount
charged for that specific fee at the time of invoice generation.
"""

from sqlalchemy import Index, Integer, Numeric

from app import db


class InvoiceLineItem(db.Model):
    """A single line item within an invoice, linked to a fee type."""

    __tablename__ = "invoice_line_items"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = db.Column(
        Integer,
        db.ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    fee_type_id = db.Column(
        Integer,
        db.ForeignKey("fee_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = db.Column(Numeric(12, 2), nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_line_item_invoice", "invoice_id"),
    )

    # Relationships
    invoice = db.relationship(
        "Invoice",
        back_populates="line_items",
        foreign_keys=[invoice_id],
    )
    fee_type = db.relationship(
        "FeeType",
        back_populates="invoice_line_items",
        foreign_keys=[fee_type_id],
    )

    def __repr__(self) -> str:
        return (
            f"<InvoiceLineItem id={self.id} invoice_id={self.invoice_id} "
            f"fee_type_id={self.fee_type_id} amount={self.amount}>"
        )
