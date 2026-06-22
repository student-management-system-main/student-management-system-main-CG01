"""
backend/seed.py
---------------
Idempotent demo dataset seed script.

Creates realistic synthetic data for demonstration and ML training purposes.
Safe to run multiple times — skips records that already exist by unique key.

Usage (from the backend/ directory):
    python seed.py

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

# ---------------------------------------------------------------------------
# Bootstrap: set env vars before importing Flask app
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "seed-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "seed-jwt-secret")

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bcrypt  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BCRYPT_ROUNDS = 4          # Fast hashing for demo; production uses 12
DEMO_PASSWORD = "demo1234"
SEED_YEAR = 2025

# Realistic Sri Lankan names
FIRST_NAMES = [
    "Thilsath", "Fazil", "Ilma", "Rahnas", "Hafsa", "Asra",
    "Akram", "Dilshan", "Kavindi", "Nimesha", "Sahan", "Thisari",
    "Mohamed", "Amara", "Buddhika", "Chamari", "Dinesh", "Eranga",
    "Fathima", "Gayan", "Hasini", "Isuru", "Janani", "Kasun",
    "Lahiru", "Malith", "Nawoda", "Oshada", "Pathum", "Qasim",
    "Rashmi", "Sampath", "Tharaka", "Udara", "Vihanga", "Waruni",
    "Xavin", "Yasiru", "Zainab", "Asel", "Bimali", "Charith",
    "Dhanuka", "Eshan", "Fonseka", "Gimhani", "Hirusha", "Ishan",
    "Jayani", "Kumari",
]
LAST_NAMES = [
    "Thilsath", "Fazil", "Fernando", "Perera", "Silva", "Jayasinghe",
    "Rajapaksa", "Bandara", "Wickrama", "Gunawardena", "Herath",
    "Dissanayake", "Amarasinghe", "Jayawardena", "Ranasinghe",
    "Senanayake", "Weerasinghe", "Liyanage", "Karunathilaka",
    "Marasinghe", "Nanayakkara", "Pathirana", "Rathnayake",
    "Siriwardena", "Thilakaratne", "Udayakumar", "Vidanagama",
    "Wimalasena", "Yatawara", "Zoysa",
]
PAYMENT_METHODS = ["bank_transfer", "credit_card", "cash", "online_portal"]


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_app():
    """Create and return a Flask app using environment config."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    from app import create_app
    # Use FLASK_ENV if set, otherwise fall back to local (SQLite) for local runs
    config_name = os.environ.get("FLASK_ENV", "local")
    return create_app(config_name)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

def seed_users(db, User):
    """Create 2 admin + 2 viewer users. Skip if email already exists."""
    users_data = [
        {"username": "admin1", "email": "admin1@demo.com", "role": "admin"},
        {"username": "admin2", "email": "admin2@demo.com", "role": "admin"},
        {"username": "staff1", "email": "staff1@demo.com", "role": "viewer"},
        {"username": "staff2", "email": "staff2@demo.com", "role": "viewer"},
    ]
    created = 0
    for u in users_data:
        if not User.query.filter_by(email=u["email"]).first():
            user = User(
                username=u["username"],
                email=u["email"],
                password_hash=_hash_password(DEMO_PASSWORD),
                role=u["role"],
                is_active=True,
            )
            db.session.add(user)
            created += 1
    db.session.commit()
    print(f"  Users: {created} created, {len(users_data) - created} skipped")


def seed_fee_types(db, FeeType):
    """Create 3 fee types. Skip if name already exists."""
    today = date.today()
    fee_data = [
        {"name": "Tuition Fee",  "amount": Decimal("5000.00"), "due_date": today + timedelta(days=30)},
        {"name": "Lab Fee",      "amount": Decimal("800.00"),  "due_date": today + timedelta(days=30)},
        {"name": "Library Fee",  "amount": Decimal("200.00"),  "due_date": today + timedelta(days=30)},
    ]
    created = 0
    for f in fee_data:
        if not FeeType.query.filter_by(name=f["name"]).first():
            ft = FeeType(
                name=f["name"],
                amount=f["amount"],
                currency="USD",
                due_date=f["due_date"],
                is_active=True,
            )
            db.session.add(ft)
            created += 1
    db.session.commit()
    print(f"  FeeTypes: {created} created, {len(fee_data) - created} skipped")


def seed_students(db, Student, User):
    """Create 50 students. ~80% active. Skip if student_number exists."""
    from app.models.user import User as UserModel
    admins = UserModel.query.filter_by(role="admin").all()
    admin_ids = [a.id for a in admins]

    today = date.today()
    created = 0
    skipped = 0

    random.seed(42)
    names_pool = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
    random.shuffle(names_pool)

    for i in range(50):
        year = SEED_YEAR - random.randint(0, 2)
        snum = f"STU-{year}-{i + 1:04d}"

        if Student.query.filter_by(student_number=snum).first():
            skipped += 1
            continue

        first, last = names_pool[i % len(names_pool)]
        email = f"{first.lower()}.{last.lower()}{i}@student.edu"
        enroll_days_ago = random.randint(30, 3 * 365)
        enroll_date = today - timedelta(days=enroll_days_ago)
        status = "inactive" if i >= 40 else "active"   # ~80% active
        assigned = random.choice(admin_ids) if admin_ids and random.random() > 0.3 else None

        student = Student(
            student_number=snum,
            first_name=first,
            last_name=last,
            email=email,
            phone=f"+947{random.randint(10000000, 99999999)}",
            enrollment_date=enroll_date,
            status=status,
            assigned_admin_id=assigned,
            sms_enabled=random.random() > 0.5,
        )
        db.session.add(student)
        created += 1

    db.session.commit()
    print(f"  Students: {created} created, {skipped} skipped")


def seed_invoices_and_transactions(db, Student, Invoice, InvoiceLineItem, FeeType, Transaction):
    """
    Create 150+ invoices and 100+ payment + 10+ reversal transactions.
    Idempotent — skips if invoice_number already exists.
    Ensures varied payment history for ML training.
    """
    from app.models.invoice_line_item import InvoiceLineItem as LineItem

    students = Student.query.all()
    fee_types = FeeType.query.all()
    if not students or not fee_types:
        print("  Skipping invoices — no students or fee types found.")
        return

    today = date.today()
    random.seed(42)

    invoices_created = 0
    txns_created = 0
    reversal_count = 0
    inv_skipped = 0

    # Status distribution: 40% paid, 25% overdue, 25% unpaid, 10% cancelled
    statuses = (
        ["paid"] * 60 +
        ["overdue"] * 37 +
        ["unpaid"] * 37 +
        ["cancelled"] * 16
    )
    random.shuffle(statuses)

    inv_index = 0
    for student in students:
        # Give each student 3 invoices on average
        n_invoices = random.randint(2, 5)
        for j in range(n_invoices):
            if inv_index >= len(statuses):
                break
            status = statuses[inv_index]
            inv_index += 1

            # Pick 1–2 fee types
            selected_fts = random.sample(fee_types, k=min(random.randint(1, 2), len(fee_types)))
            total_amount = sum(ft.amount for ft in selected_fts)

            # Due date: spread -12 to +3 months
            offset_days = random.randint(-365, 90)
            due_date = today + timedelta(days=offset_days)

            # Generate unique invoice number
            inv_num = f"INV-SEED-{student.id:04d}-{j + 1:03d}"
            if Invoice.query.filter_by(invoice_number=inv_num).first():
                inv_skipped += 1
                continue

            paid_at = None
            outstanding = total_amount

            if status == "paid":
                paid_at = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180))
                outstanding = Decimal("0.00")
            elif status == "cancelled":
                outstanding = total_amount
            elif status == "overdue":
                # Partially paid sometimes (for ML variety)
                if random.random() > 0.6:
                    outstanding = total_amount * Decimal(str(round(random.uniform(0.3, 0.9), 2)))

            invoice = Invoice(
                invoice_number=inv_num,
                student_id=student.id,
                total_amount=total_amount,
                outstanding_balance=outstanding,
                status=status,
                due_date=due_date,
                paid_at=paid_at,
            )
            db.session.add(invoice)
            db.session.flush()

            # Line items
            for ft in selected_fts:
                li = LineItem(invoice_id=invoice.id, fee_type_id=ft.id, amount=ft.amount)
                db.session.add(li)

            invoices_created += 1

            # Create transactions for paid/partially-paid invoices
            if status == "paid":
                ref = f"TXN-SEED-{invoice.id:06d}-P"
                if not Transaction.query.filter_by(transaction_ref=ref).first():
                    txn = Transaction(
                        transaction_ref=ref,
                        student_id=student.id,
                        invoice_id=invoice.id,
                        amount=total_amount,
                        payment_method=random.choice(PAYMENT_METHODS),
                        type="payment",
                    )
                    db.session.add(txn)
                    txns_created += 1

                    # Create a reversal for ~10% of paid invoices
                    if reversal_count < 15 and random.random() > 0.9:
                        rev_ref = f"TXN-SEED-{invoice.id:06d}-R"
                        if not Transaction.query.filter_by(transaction_ref=rev_ref).first():
                            rev = Transaction(
                                transaction_ref=rev_ref,
                                student_id=student.id,
                                invoice_id=invoice.id,
                                amount=total_amount,
                                payment_method=random.choice(PAYMENT_METHODS),
                                type="reversal",
                                reversal_of=txn.id,
                            )
                            db.session.add(rev)
                            reversal_count += 1
                            txns_created += 1

            elif status == "overdue" and outstanding < total_amount:
                # Partial payment on overdue invoice
                paid_amount = total_amount - outstanding
                ref = f"TXN-SEED-{invoice.id:06d}-PP"
                if not Transaction.query.filter_by(transaction_ref=ref).first():
                    txn = Transaction(
                        transaction_ref=ref,
                        student_id=student.id,
                        invoice_id=invoice.id,
                        amount=paid_amount,
                        payment_method=random.choice(PAYMENT_METHODS),
                        type="payment",
                    )
                    db.session.add(txn)
                    txns_created += 1

    db.session.commit()
    print(f"  Invoices: {invoices_created} created, {inv_skipped} skipped")
    print(f"  Transactions: {txns_created} created ({reversal_count} reversals)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Starting demo seed...")
    app = get_app()

    with app.app_context():
        from app import db
        from app.models.fee_type import FeeType
        from app.models.invoice import Invoice
        from app.models.invoice_line_item import InvoiceLineItem
        from app.models.student import Student
        from app.models.transaction import Transaction
        from app.models.user import User

        print("Seeding users...")
        seed_users(db, User)

        print("Seeding fee types...")
        seed_fee_types(db, FeeType)

        print("Seeding students...")
        seed_students(db, Student, User)

        print("Seeding invoices and transactions...")
        seed_invoices_and_transactions(db, Student, Invoice, InvoiceLineItem, FeeType, Transaction)

        # Summary
        print("\n--- Seed complete ---")
        print(f"  Users:        {User.query.count()}")
        print(f"  FeeTypes:     {FeeType.query.count()}")
        print(f"  Students:     {Student.query.count()} "
              f"({Student.query.filter_by(status='active').count()} active)")
        print(f"  Invoices:     {Invoice.query.count()}")
        print(f"  Transactions: {Transaction.query.count()} "
              f"({Transaction.query.filter_by(type='payment').count()} payments, "
              f"{Transaction.query.filter_by(type='reversal').count()} reversals)")
        print("\nLogin credentials:")
        print("  admin1@demo.com / demo1234  (admin)")
        print("  admin2@demo.com / demo1234  (admin)")
        print("  staff1@demo.com / demo1234  (viewer)")
        print("  staff2@demo.com / demo1234  (viewer)")
        print("\nRun `POST /retrain` on the Risk Service to train ML models.")


if __name__ == "__main__":
    main()
