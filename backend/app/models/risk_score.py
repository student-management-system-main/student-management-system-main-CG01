"""
RiskScore ORM model.

Stores the AI-computed risk score for a student at a point in time.
Each scoring run produces a new row; the latest row is the current score.
"""

from sqlalchemy import DateTime, Enum, Index, Integer, Numeric, String, func

from app import db


class RiskScore(db.Model):
    """A point-in-time AI risk score for a student."""

    __tablename__ = "risk_scores"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(
        Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    score = db.Column(Numeric(5, 2), nullable=False)
    risk_category = db.Column(
        Enum("low", "medium", "high", name="risk_category_enum"),
        nullable=False,
    )
    model_version = db.Column(String(50), nullable=False)
    computed_at = db.Column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_risk_student", "student_id"),
        Index("idx_risk_computed_at", "computed_at"),
    )

    # Relationships
    student = db.relationship(
        "Student",
        back_populates="risk_scores",
        foreign_keys=[student_id],
    )

    def __repr__(self) -> str:
        return (
            f"<RiskScore id={self.id} student_id={self.student_id} "
            f"score={self.score} category={self.risk_category!r} "
            f"version={self.model_version!r}>"
        )
