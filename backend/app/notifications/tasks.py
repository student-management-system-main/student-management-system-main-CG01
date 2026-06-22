"""
Celery notification tasks.

Provides all notification tasks for the fee management system:

    - send_overdue_reminder(invoice_id)      — email + optional SMS to student
    - send_7day_reminder(invoice_id)         — email to student + assigned admin
    - send_30day_escalation(invoice_id)      — email to all admin users
    - suppress_reminders(invoice_id)         — revoke all scheduled tasks for invoice
    - retry_failed_notification(log_id)      — exponential-backoff retry (max 3)
    - admin_notification_task(student_id, new_category) — risk escalation alert

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

import logging

from celery.exceptions import MaxRetriesExceededError
from flask import current_app

from app import celery, db
from app.notifications.providers import send_email, send_sms

logger = logging.getLogger(__name__)

# In-memory key template for storing scheduled task IDs per invoice
# (for local development; use Redis in production)
_REMINDERS_KEY = "reminders:{invoice_id}"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def write_notification_log(
    actor_id,
    recipient: str,
    channel: str,
    delivery_status: str,
    resource_id,
    resource_type: str = "invoice",
) -> None:
    """
    Append a notification log entry to the ``logs`` table.

    Parameters
    ----------
    actor_id:
        ID of the user/task that triggered the notification (may be None for
        system-generated events).
    recipient:
        Email address or phone number the notification was sent to.
    channel:
        ``'email'`` or ``'sms'``.
    delivery_status:
        ``'sent'`` or ``'failed'``.
    resource_id:
        ID of the Invoice (or other resource) that triggered the notification.
    resource_type:
        Type of the resource (default ``'invoice'``; use ``'student'`` for
        risk-escalation notifications that are not tied to a specific invoice).
    """
    from app.models.log import Log  # noqa: PLC0415

    log_entry = Log(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action="notification_sent",
        channel=channel,
        delivery_status=delivery_status,
        new_values={"recipient": recipient},
    )
    db.session.add(log_entry)
    db.session.commit()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@celery.task
def send_overdue_reminder(invoice_id: int) -> dict:
    """
    Send an overdue payment reminder to the student.

    - Always sends an email.
    - Sends an SMS if the student has ``sms_enabled = True``.
    - Logs both attempts to the ``logs`` table.

    Requirements: 5.1, 5.2
    """
    from app.models.invoice import Invoice  # noqa: PLC0415
    from app.models.student import Student  # noqa: PLC0415

    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        logger.warning("send_overdue_reminder: invoice %s not found", invoice_id)
        return {"error": "invoice_not_found"}

    student = db.session.get(Student, invoice.student_id)
    if student is None:
        logger.warning("send_overdue_reminder: student for invoice %s not found", invoice_id)
        return {"error": "student_not_found"}

    message = (
        f"Dear {student.first_name} {student.last_name},\n\n"
        f"Your invoice {invoice.invoice_number} is overdue. "
        f"The outstanding balance is {invoice.outstanding_balance}. "
        f"Please arrange payment as soon as possible.\n\n"
        f"Thank you."
    )

    # --- Email ---
    email_ok = send_email(student.email, "Payment Overdue", message)
    write_notification_log(
        actor_id=None,
        recipient=student.email,
        channel="email",
        delivery_status="sent" if email_ok else "failed",
        resource_id=invoice_id,
    )

    # --- SMS (conditional) ---
    sms_ok = None
    if student.sms_enabled and student.phone:
        sms_ok = send_sms(student.phone, message)
        write_notification_log(
            actor_id=None,
            recipient=student.phone,
            channel="sms",
            delivery_status="sent" if sms_ok else "failed",
            resource_id=invoice_id,
        )

    logger.info(
        "send_overdue_reminder: invoice=%s email_ok=%s sms_ok=%s",
        invoice_id,
        email_ok,
        sms_ok,
    )
    return {"email_ok": email_ok, "sms_ok": sms_ok}


@celery.task
def send_7day_reminder(invoice_id: int) -> dict:
    """
    Send a 7-day overdue reminder to the student and the assigned admin.

    Logs both email attempts.

    Requirements: 5.3
    """
    from app.models.invoice import Invoice  # noqa: PLC0415
    from app.models.student import Student  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415

    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        logger.warning("send_7day_reminder: invoice %s not found", invoice_id)
        return {"error": "invoice_not_found"}

    student = db.session.get(Student, invoice.student_id)
    if student is None:
        logger.warning("send_7day_reminder: student for invoice %s not found", invoice_id)
        return {"error": "student_not_found"}

    student_message = (
        f"Dear {student.first_name} {student.last_name},\n\n"
        f"Your invoice {invoice.invoice_number} has been overdue for 7 days. "
        f"The outstanding balance is {invoice.outstanding_balance}. "
        f"Please make payment immediately to avoid further action.\n\n"
        f"Thank you."
    )

    # --- Email to student ---
    student_email_ok = send_email(student.email, "Payment Overdue — 7 Day Notice", student_message)
    write_notification_log(
        actor_id=None,
        recipient=student.email,
        channel="email",
        delivery_status="sent" if student_email_ok else "failed",
        resource_id=invoice_id,
    )

    # --- Email to assigned admin ---
    admin_email_ok = None
    if student.assigned_admin_id:
        admin = db.session.get(User, student.assigned_admin_id)
        if admin:
            admin_message = (
                f"Invoice {invoice.invoice_number} for student "
                f"{student.first_name} {student.last_name} has been overdue for 7 days. "
                f"Outstanding balance: {invoice.outstanding_balance}. "
                f"Please follow up."
            )
            admin_email_ok = send_email(
                admin.email,
                f"7-Day Overdue Alert — Invoice {invoice.invoice_number}",
                admin_message,
            )
            write_notification_log(
                actor_id=None,
                recipient=admin.email,
                channel="email",
                delivery_status="sent" if admin_email_ok else "failed",
                resource_id=invoice_id,
            )

    logger.info(
        "send_7day_reminder: invoice=%s student_email_ok=%s admin_email_ok=%s",
        invoice_id,
        student_email_ok,
        admin_email_ok,
    )
    return {"student_email_ok": student_email_ok, "admin_email_ok": admin_email_ok}


@celery.task
def send_30day_escalation(invoice_id: int) -> dict:
    """
    Escalate a 30-day overdue invoice by emailing all admin users.

    Requirements: 5.4
    """
    from app.models.invoice import Invoice  # noqa: PLC0415
    from app.models.student import Student  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415

    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        logger.warning("send_30day_escalation: invoice %s not found", invoice_id)
        return {"error": "invoice_not_found"}

    student = db.session.get(Student, invoice.student_id)
    if student is None:
        logger.warning("send_30day_escalation: student for invoice %s not found", invoice_id)
        return {"error": "student_not_found"}

    admins = db.session.query(User).filter(User.role == "admin", User.is_active == True).all()  # noqa: E712
    if not admins:
        logger.warning("send_30day_escalation: no active admin users found")
        return {"error": "no_admins"}

    subject = f"ESCALATION — Invoice {invoice.invoice_number} Overdue 30 Days"
    results = []
    for admin in admins:
        admin_message = (
            f"ESCALATION NOTICE\n\n"
            f"Invoice {invoice.invoice_number} for student "
            f"{student.first_name} {student.last_name} (ID: {student.student_number}) "
            f"has been overdue for 30 days.\n"
            f"Outstanding balance: {invoice.outstanding_balance}.\n"
            f"Immediate action is required."
        )
        ok = send_email(admin.email, subject, admin_message)
        write_notification_log(
            actor_id=None,
            recipient=admin.email,
            channel="email",
            delivery_status="sent" if ok else "failed",
            resource_id=invoice_id,
        )
        results.append({"admin_id": admin.id, "email": admin.email, "ok": ok})

    logger.info("send_30day_escalation: invoice=%s sent to %d admins", invoice_id, len(admins))
    return {"results": results}


@celery.task
def suppress_reminders(invoice_id: int) -> dict:
    """
    Revoke all scheduled Celery reminder tasks for a given invoice.

    Task IDs are stored in an in-memory registry (or Redis in production)
    under the key ``reminders:{invoice_id}`` and each stored ID is revoked
    via ``celery.control.revoke(task_id, terminate=True)``.

    Requirements: 5.7
    """
    from app import _task_reminders  # noqa: PLC0415

    # Get task IDs from in-memory registry
    task_ids = _task_reminders.get(invoice_id, [])

    revoked = []
    for task_id in task_ids:
        try:
            celery.control.revoke(task_id, terminate=True)
            revoked.append(task_id)
            logger.info("suppress_reminders: revoked task %s for invoice %s", task_id, invoice_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "suppress_reminders: could not revoke task %s for invoice %s: %s",
                task_id,
                invoice_id,
                exc,
            )

    # Clean up the in-memory registry entry
    if invoice_id in _task_reminders:
        del _task_reminders[invoice_id]

    logger.info("suppress_reminders: invoice=%s revoked %d tasks", invoice_id, len(revoked))
    return {"revoked": revoked}


@celery.task(bind=True, max_retries=3)
def retry_failed_notification(self, log_id: int) -> dict:
    """
    Re-attempt delivery of a previously failed notification.

    Loads the Log record identified by ``log_id``, extracts the channel
    (``'email'`` or ``'sms'``) and recipient, then retries delivery.

    Retry schedule (exponential backoff):
        Attempt 1 →  2 min
        Attempt 2 →  4 min
        Attempt 3 →  8 min

    After the third failure the log record's ``delivery_status`` is updated
    to ``'failed'``.

    Requirements: 5.5
    """
    from app.models.log import Log  # noqa: PLC0415

    log_record = db.session.get(Log, log_id)
    if log_record is None:
        logger.warning("retry_failed_notification: log %s not found", log_id)
        return {"error": "log_not_found"}

    channel = log_record.channel
    recipient = (log_record.new_values or {}).get("recipient") if log_record.new_values else None

    if not channel or not recipient:
        logger.error(
            "retry_failed_notification: log %s missing channel or recipient", log_id
        )
        return {"error": "missing_channel_or_recipient"}

    # Re-attempt delivery
    if channel == "email":
        subject = "Payment Notification"
        body = "Please check your outstanding invoices."
        ok = send_email(recipient, subject, body)
    elif channel == "sms":
        body = "You have outstanding invoices. Please check your account."
        ok = send_sms(recipient, body)
    else:
        logger.error(
            "retry_failed_notification: unknown channel %r for log %s", channel, log_id
        )
        return {"error": f"unknown_channel:{channel}"}

    if ok:
        # Update delivery_status to 'sent' — we create a new log entry since
        # the logs table is append-only; note: we cannot mutate log_record itself
        write_notification_log(
            actor_id=None,
            recipient=recipient,
            channel=channel,
            delivery_status="sent",
            resource_id=log_record.resource_id,
        )
        logger.info("retry_failed_notification: log=%s succeeded on retry", log_id)
        return {"status": "sent"}

    # Delivery failed — retry with exponential backoff
    retries = self.request.retries
    countdown_seconds = 2 * (2 ** retries) * 60  # 2 min, 4 min, 8 min

    try:
        logger.warning(
            "retry_failed_notification: log=%s attempt %d/%d failed; retrying in %ds",
            log_id,
            retries + 1,
            self.max_retries + 1,
            countdown_seconds,
        )
        raise self.retry(countdown=countdown_seconds)
    except MaxRetriesExceededError:
        # Final failure — log as permanently failed
        logger.error(
            "retry_failed_notification: log=%s exhausted all retries; marking failed",
            log_id,
        )
        write_notification_log(
            actor_id=None,
            recipient=recipient,
            channel=channel,
            delivery_status="failed",
            resource_id=log_record.resource_id,
        )
        return {"status": "failed"}


@celery.task
def admin_notification_task(student_id: int, new_category: str) -> dict:
    """
    Notify the assigned admin when a student's risk category escalates.

    Queries the student and their assigned admin, then sends an email
    informing the admin of the escalation.

    Requirements: 4.5
    """
    from app.models.student import Student  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415

    student = db.session.get(Student, student_id)
    if student is None:
        logger.warning("admin_notification_task: student %s not found", student_id)
        return {"error": "student_not_found"}

    if not student.assigned_admin_id:
        logger.info(
            "admin_notification_task: student %s has no assigned admin; skipping",
            student_id,
        )
        return {"status": "no_assigned_admin"}

    admin = db.session.get(User, student.assigned_admin_id)
    if admin is None:
        logger.warning(
            "admin_notification_task: assigned admin %s not found for student %s",
            student.assigned_admin_id,
            student_id,
        )
        return {"error": "admin_not_found"}

    subject = f"Risk Escalation Alert — Student {student.student_number}"
    message = (
        f"Dear {admin.username},\n\n"
        f"The risk category for student {student.first_name} {student.last_name} "
        f"(Student No: {student.student_number}) has escalated to "
        f"'{new_category.upper()}'.\n\n"
        f"Please review their account and take appropriate action.\n\n"
        f"Thank you."
    )

    ok = send_email(admin.email, subject, message)
    write_notification_log(
        actor_id=None,
        recipient=admin.email,
        channel="email",
        delivery_status="sent" if ok else "failed",
        resource_id=student_id,
        resource_type="student",
    )

    logger.info(
        "admin_notification_task: student=%s new_category=%s admin=%s email_ok=%s",
        student_id,
        new_category,
        admin.id,
        ok,
    )
    return {"email_ok": ok, "admin_id": admin.id}
