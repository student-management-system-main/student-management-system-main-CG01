"""
User ORM model.

Represents an authenticated system user (Admin or Viewer).
Passwords are stored as bcrypt hashes; never store plain-text passwords.
"""

import bcrypt
from flask import current_app
from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func

from app import db


class User(db.Model):
    """System user with role-based access control."""

    __tablename__ = "users"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    username = db.Column(String(80), unique=True, nullable=False)
    email = db.Column(String(255), unique=True, nullable=False)
    password_hash = db.Column(String(255), nullable=False)
    role = db.Column(
        Enum("admin", "viewer", name="user_role_enum"),
        nullable=False,
        default="viewer",
        server_default="viewer",
    )
    is_active = db.Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at = db.Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    assigned_students = db.relationship(
        "Student",
        back_populates="assigned_admin",
        foreign_keys="Student.assigned_admin_id",
        lazy="dynamic",
    )
    audit_logs = db.relationship(
        "Log",
        back_populates="actor",
        foreign_keys="Log.actor_id",
        lazy="dynamic",
    )

    def set_password(self, plain: str) -> None:
        """Hash *plain* with bcrypt and store the result.

        The bcrypt cost factor is read from the Flask app config key
        ``BCRYPT_LOG_ROUNDS`` (default 12, per Requirement 8.7).
        """
        rounds: int = current_app.config.get("BCRYPT_LOG_ROUNDS", 12)
        self.password_hash = bcrypt.hashpw(
            plain.encode("utf-8"), bcrypt.gensalt(rounds=rounds)
        ).decode("utf-8")

    def check_password(self, plain: str) -> bool:
        """Return True if *plain* matches the stored bcrypt hash."""
        return bcrypt.checkpw(
            plain.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def to_dict(self) -> dict:
        """Return a safe representation of the user (no password_hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def find_by_username(cls, username: str) -> "User | None":
        """Return the User with the given username, or None if not found."""
        return cls.query.filter_by(username=username).first()

    @classmethod
    def find_by_email(cls, email: str) -> "User | None":
        """Return the User with the given email, or None if not found."""
        return cls.query.filter_by(email=email).first()

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
