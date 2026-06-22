"""
Student ORM model.

Represents an enrolled student whose fee records are tracked by the system.
"""

from sqlalchemy import Boolean, Date, DateTime, Enum, Index, Integer, String, func

from app import db


class Student(db.Model):
    """Enrolled student with fee tracking and risk scoring."""

    __tablename__ = "students"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    student_number = db.Column(String(50), unique=True, nullable=False)
    first_name = db.Column(String(100), nullable=False)
    last_name = db.Column(String(100), nullable=False)
    email = db.Column(String(255), nullable=False)
    phone = db.Column(String(30), nullable=True)
    enrollment_date = db.Column(Date, nullable=False)
    status = db.Column(
        Enum("active", "inactive", name="student_status_enum"),
        nullable=False,
        default="active",
        server_default="active",
    )
    assigned_admin_id = db.Column(
        Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sms_enabled = db.Column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at = db.Column(DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes
    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_assigned_admin", "assigned_admin_id"),
    )

    # Relationships
    assigned_admin = db.relationship(
        "User",
        back_populates="assigned_students",
        foreign_keys=[assigned_admin_id],
    )
    invoices = db.relationship(
        "Invoice",
        back_populates="student",
        foreign_keys="Invoice.student_id",
        lazy="dynamic",
    )
    transactions = db.relationship(
        "Transaction",
        back_populates="student",
        foreign_keys="Transaction.student_id",
        lazy="dynamic",
    )
    risk_scores = db.relationship(
        "RiskScore",
        back_populates="student",
        foreign_keys="RiskScore.student_id",
        lazy="dynamic",
        order_by="RiskScore.computed_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<Student id={self.id} number={self.student_number!r} "
            f"name={self.first_name!r} {self.last_name!r} status={self.status!r}>"
        )
