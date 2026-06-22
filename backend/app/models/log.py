"""
Log ORM model (append-only audit log).

Records every create, update, deactivate, export, and notification event.
Rows are NEVER modified or deleted after insertion — this is enforced at
both the ORM layer (no update/delete routes) and the DB layer (no UPDATE/
DELETE privileges on this table in production).
"""

from sqlalchemy import DateTime, Index, Integer, JSON, String, func

from app import db


class Log(db.Model):
    """Append-only audit and notification log entry."""

    __tablename__ = "logs"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    # Nullable: system-generated actions (e.g., scheduled tasks) have no actor
    actor_id = db.Column(
        Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resource_type = db.Column(String(80), nullable=True)
    resource_id = db.Column(Integer, nullable=True)
    action = db.Column(String(80), nullable=False)
    previous_values = db.Column(JSON, nullable=True)
    new_values = db.Column(JSON, nullable=True)
    # Notification-specific fields
    channel = db.Column(String(20), nullable=True)          # 'email' | 'sms'
    delivery_status = db.Column(String(20), nullable=True)  # 'sent' | 'failed'
    # Append-only — no updated_at column
    created_at = db.Column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_log_actor", "actor_id"),
        Index("idx_log_resource", "resource_type", "resource_id"),
        Index("idx_log_created_at", "created_at"),
    )

    # Relationships
    actor = db.relationship(
        "User",
        back_populates="audit_logs",
        foreign_keys=[actor_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Log id={self.id} actor_id={self.actor_id} "
            f"action={self.action!r} resource={self.resource_type!r}:{self.resource_id}>"
        )
