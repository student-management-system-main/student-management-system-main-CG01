"""
Celery periodic tasks for invoice lifecycle management.

Provides:
    - ``check_overdue_invoices()`` — Celery Beat task (hourly) that transitions
      unpaid invoices whose due date has passed to "overdue" status, enqueues
      an immediate overdue reminder, and schedules 7-day and 30-day follow-up
      tasks, storing their IDs in an in-memory registry (or Redis in production)
      for later suppression.

Requirements: 2.4, 5.1
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import current_app

from app import celery, db

logger = logging.getLogger(__name__)

# In-memory task reminder registry key template
# For production, use Redis instead
_REMINDERS_KEY = "reminders:{invoice_id}"


@celery.task
def check_overdue_invoices() -> dict:
    """
    Transition all unpaid-but-past-due invoices to "overdue" and kick off the
    notification cascade for each one.

    For every Invoice where ``status == 'unpaid'`` and ``due_date < today``:

    1. Set ``invoice.status = 'overdue'``.
    2. Enqueue ``send_overdue_reminder`` immediately (Requirement 5.1).
    3. Schedule ``send_7day_reminder`` via ETA = now + 7 days (Requirement 5.3).
    4. Schedule ``send_30day_escalation`` via ETA = now + 30 days (Requirement 5.4).
    5. Store both scheduled task IDs in Redis under ``reminders:{invoice.id}``
       so that ``suppress_reminders`` can revoke them when the invoice is paid
       (Requirement 5.7).

    All status changes are committed in a single database transaction
    (bulk commit) to minimise round-trips.

    Returns
    -------
    dict
        ``{"updated_count": int, "invoice_ids": [int, ...]}``

    Requirements: 2.4, 5.1
    """
    from app.models.invoice import Invoice  # noqa: PLC0415 (avoid circular import)
    from app.notifications.tasks import (  # noqa: PLC0415
        send_overdue_reminder,
        send_7day_reminder,
        send_30day_escalation,
    )

    now = datetime.now(timezone.utc)
    today = now.date()

    # ------------------------------------------------------------------
    # Query all unpaid invoices whose due date has already passed
    # ------------------------------------------------------------------
    overdue_invoices = (
        db.session.query(Invoice)
        .filter(
            Invoice.status == "unpaid",
            Invoice.due_date < today,
        )
        .all()
    )

    if not overdue_invoices:
        logger.info("check_overdue_invoices: no unpaid overdue invoices found")
        return {"updated_count": 0, "invoice_ids": []}

    updated_ids: list[int] = []

    for invoice in overdue_invoices:
        # ------------------------------------------------------------------
        # 1. Mark invoice as overdue
        # ------------------------------------------------------------------
        invoice.status = "overdue"
        updated_ids.append(invoice.id)

        # ------------------------------------------------------------------
        # 2. Immediate overdue reminder
        # ------------------------------------------------------------------
        send_overdue_reminder.delay(invoice.id)

        # ------------------------------------------------------------------
        # 3 & 4. Scheduled follow-up reminders with ETA
        # ------------------------------------------------------------------
        eta_7day = now + timedelta(days=7)
        eta_30day = now + timedelta(days=30)

        result_7day = send_7day_reminder.apply_async(
            args=[invoice.id],
            eta=eta_7day,
        )
        result_30day = send_30day_escalation.apply_async(
            args=[invoice.id],
            eta=eta_30day,
        )

        # ------------------------------------------------------------------
        # 5. Store scheduled task IDs in in-memory registry for later suppression
        # ------------------------------------------------------------------
        from app import _task_reminders  # noqa: PLC0415
        if invoice.id not in _task_reminders:
            _task_reminders[invoice.id] = []
        _task_reminders[invoice.id].append(result_7day.id)
        _task_reminders[invoice.id].append(result_30day.id)
        logger.debug(
            "check_overdue_invoices: stored reminder task IDs for invoice %s "
            "(7d=%s, 30d=%s)",
            invoice.id,
            result_7day.id,
            result_30day.id,
        )

    # ------------------------------------------------------------------
    # Bulk commit — single database round-trip for all status changes
    # ------------------------------------------------------------------
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "check_overdue_invoices: DB commit failed for %d invoices: %s",
            len(overdue_invoices),
            exc,
        )
        raise

    logger.info(
        "check_overdue_invoices: marked %d invoice(s) as overdue — ids=%s",
        len(updated_ids),
        updated_ids,
    )
    return {"updated_count": len(updated_ids), "invoice_ids": updated_ids}
