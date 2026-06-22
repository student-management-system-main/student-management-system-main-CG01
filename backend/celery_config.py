"""
Celery Beat schedule configuration.

Defines all periodic tasks for the Fee Management System.
Imported by the application factory and celery_worker.py.

Requirements: 2.4, 4.7
"""

from celery.schedules import crontab

beat_schedule = {
    # Check for overdue invoices every hour at :00 (Requirement 2.4)
    "check-overdue-invoices-hourly": {
        "task": "app.invoices.tasks.check_overdue_invoices",
        "schedule": crontab(minute=0),  # every hour on the hour
    },
    # Nightly batch risk scoring — default midnight, overridden by BATCH_SCORE_CRON
    # The actual schedule is applied in _configure_celery() after reading app config.
    "batch-risk-scoring-nightly": {
        "task": "app.risk.tasks.batch_risk_scoring_task",
        "schedule": crontab(hour=0, minute=0),  # daily at midnight (default)
    },
}
