"""
Dashboard blueprint routes.

Endpoints
---------
GET /api/v1/dashboard/summary — KPI summary for the finance dashboard

Requirements: 9.1
"""

import logging
from datetime import date, timedelta

from flask import Blueprint, jsonify

from app import db
from app.auth.decorators import viewer_or_admin_required
from app.models.invoice import Invoice
from app.models.student import Student

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/summary
# ---------------------------------------------------------------------------

@dashboard_bp.route("/summary", methods=["GET"])
@viewer_or_admin_required
def get_summary():
    """
    Return KPI summary figures for the dashboard.

    Fields returned
    ---------------
    total_collected      : sum of ``total_amount`` for all ``paid`` invoices
    total_outstanding    : sum of ``outstanding_balance`` for ``unpaid`` and
                           ``overdue`` invoices
    overdue_count        : count of invoices with ``status = 'overdue'``
    active_student_count : count of students with ``status = 'active'``
    forecast_30d         : sum of ``outstanding_balance`` for invoices whose
                           ``due_date`` falls between today and today + 30 days
                           (inclusive on both ends)

    All decimal amounts are serialised as strings to preserve precision.

    Requirements: 9.1
    """
    try:
        today = date.today()
        forecast_end = today + timedelta(days=30)

        # total_collected = SUM(total_amount) WHERE status = 'paid'
        total_collected = (
            db.session.query(
                db.func.coalesce(db.func.sum(Invoice.total_amount), 0)
            )
            .filter(Invoice.status == "paid")
            .scalar()
        )

        # total_outstanding = SUM(outstanding_balance) WHERE status IN ('unpaid', 'overdue')
        total_outstanding = (
            db.session.query(
                db.func.coalesce(db.func.sum(Invoice.outstanding_balance), 0)
            )
            .filter(Invoice.status.in_(["unpaid", "overdue"]))
            .scalar()
        )

        # overdue_count = COUNT(*) WHERE status = 'overdue'
        overdue_count = (
            db.session.query(db.func.count(Invoice.id))
            .filter(Invoice.status == "overdue")
            .scalar()
        )

        # active_student_count = COUNT(*) FROM students WHERE status = 'active'
        active_student_count = (
            db.session.query(db.func.count(Student.id))
            .filter(Student.status == "active")
            .scalar()
        )

        # forecast_30d = SUM(outstanding_balance) WHERE due_date BETWEEN today AND today+30d
        forecast_30d = (
            db.session.query(
                db.func.coalesce(db.func.sum(Invoice.outstanding_balance), 0)
            )
            .filter(
                Invoice.due_date >= today,
                Invoice.due_date <= forecast_end,
            )
            .scalar()
        )

        return (
            jsonify(
                {
                    "data": {
                        "total_collected": f"{total_collected:.2f}",
                        "total_outstanding": f"{total_outstanding:.2f}",
                        "overdue_count": int(overdue_count),
                        "active_student_count": int(active_student_count),
                        "forecast_30d": f"{forecast_30d:.2f}",
                    }
                }
            ),
            200,
        )

    except Exception as exc:
        logger.exception("Dashboard summary query failed: %s", exc)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Failed to compute dashboard summary. Please try again.",
                        "details": {},
                    }
                }
            ),
            500,
        )
