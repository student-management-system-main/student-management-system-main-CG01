"""Initial schema — create all 7 tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

Creates the complete database schema for the Fee Management System,
including all ENUM types, tables, indexes, and foreign-key constraints
exactly as defined in the SQLAlchemy models.

Tables created (in dependency order):
  1. users
  2. students
  3. fee_types
  4. invoices
  5. invoice_line_items
  6. transactions
  7. risk_scores
  8. logs
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables, ENUM types, indexes, and FK constraints."""

    # ------------------------------------------------------------------
    # ENUM types (MySQL / PostgreSQL)
    # ------------------------------------------------------------------
    # SQLAlchemy will create these inline for MySQL; for PostgreSQL they
    # need to be created as standalone types first.  We use
    # sa.Enum(..., create_constraint=True) in the column definitions
    # which handles both dialects correctly.

    user_role_enum = sa.Enum("admin", "viewer", name="user_role_enum")
    student_status_enum = sa.Enum("active", "inactive", name="student_status_enum")
    invoice_status_enum = sa.Enum(
        "unpaid", "overdue", "paid", "cancelled", name="invoice_status_enum"
    )
    transaction_type_enum = sa.Enum(
        "payment", "reversal", name="transaction_type_enum"
    )
    risk_category_enum = sa.Enum("low", "medium", "high", name="risk_category_enum")

    # ------------------------------------------------------------------
    # 1. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="viewer",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    # ------------------------------------------------------------------
    # 2. students
    # ------------------------------------------------------------------
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_number", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("enrollment_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            student_status_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=True),
        sa.Column(
            "sms_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_admin_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_number"),
    )
    op.create_index("idx_status", "students", ["status"], unique=False)
    op.create_index(
        "idx_assigned_admin", "students", ["assigned_admin_id"], unique=False
    )

    # ------------------------------------------------------------------
    # 3. fee_types
    # ------------------------------------------------------------------
    op.create_table(
        "fee_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # 4. invoices
    # ------------------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column(
            "total_amount", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "outstanding_balance",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "status",
            invoice_status_enum,
            nullable=False,
            server_default="unpaid",
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index(
        "idx_invoice_student", "invoices", ["student_id"], unique=False
    )
    op.create_index(
        "idx_invoice_status", "invoices", ["status"], unique=False
    )
    op.create_index(
        "idx_invoice_due_date", "invoices", ["due_date"], unique=False
    )

    # ------------------------------------------------------------------
    # 5. invoice_line_items
    # ------------------------------------------------------------------
    op.create_table(
        "invoice_line_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("fee_type_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fee_type_id"],
            ["fee_types.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_line_item_invoice", "invoice_line_items", ["invoice_id"], unique=False
    )

    # ------------------------------------------------------------------
    # 6. transactions
    # ------------------------------------------------------------------
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("transaction_ref", sa.String(length=80), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column(
            "type",
            transaction_type_enum,
            nullable=False,
            server_default="payment",
        ),
        sa.Column("reversal_of", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of"],
            ["transactions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_ref"),
    )
    op.create_index(
        "idx_transaction_student", "transactions", ["student_id"], unique=False
    )
    op.create_index(
        "idx_transaction_invoice", "transactions", ["invoice_id"], unique=False
    )

    # ------------------------------------------------------------------
    # 7. risk_scores
    # ------------------------------------------------------------------
    op.create_table(
        "risk_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "risk_category",
            risk_category_enum,
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_risk_student", "risk_scores", ["student_id"], unique=False
    )
    op.create_index(
        "idx_risk_computed_at", "risk_scores", ["computed_at"], unique=False
    )

    # ------------------------------------------------------------------
    # 8. logs  (append-only audit log)
    # ------------------------------------------------------------------
    op.create_table(
        "logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("previous_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("delivery_status", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_log_actor", "logs", ["actor_id"], unique=False)
    op.create_index(
        "idx_log_resource", "logs", ["resource_type", "resource_id"], unique=False
    )
    op.create_index("idx_log_created_at", "logs", ["created_at"], unique=False)


def downgrade() -> None:
    """Drop all tables and ENUM types in reverse dependency order."""

    # Drop indexes and tables in reverse creation order
    op.drop_index("idx_log_created_at", table_name="logs")
    op.drop_index("idx_log_resource", table_name="logs")
    op.drop_index("idx_log_actor", table_name="logs")
    op.drop_table("logs")

    op.drop_index("idx_risk_computed_at", table_name="risk_scores")
    op.drop_index("idx_risk_student", table_name="risk_scores")
    op.drop_table("risk_scores")

    op.drop_index("idx_transaction_invoice", table_name="transactions")
    op.drop_index("idx_transaction_student", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("idx_line_item_invoice", table_name="invoice_line_items")
    op.drop_table("invoice_line_items")

    op.drop_index("idx_invoice_due_date", table_name="invoices")
    op.drop_index("idx_invoice_status", table_name="invoices")
    op.drop_index("idx_invoice_student", table_name="invoices")
    op.drop_table("invoices")

    op.drop_table("fee_types")

    op.drop_index("idx_assigned_admin", table_name="students")
    op.drop_index("idx_status", table_name="students")
    op.drop_table("students")

    op.drop_table("users")

    # Drop ENUM types (PostgreSQL only — MySQL drops them with the table)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="risk_category_enum").drop(bind, checkfirst=True)
        sa.Enum(name="transaction_type_enum").drop(bind, checkfirst=True)
        sa.Enum(name="invoice_status_enum").drop(bind, checkfirst=True)
        sa.Enum(name="student_status_enum").drop(bind, checkfirst=True)
        sa.Enum(name="user_role_enum").drop(bind, checkfirst=True)
