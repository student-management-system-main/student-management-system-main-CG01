"""
Celery worker entry point for the Fee Management System.

Usage:
    celery -A celery_worker.celery worker --loglevel=info
    celery -A celery_worker.celery beat --loglevel=info   # for scheduled tasks
"""

import os

import celery_config  # noqa: F401 – ensures beat_schedule is importable
from app import create_app, celery  # noqa: F401 – re-exported for Celery CLI

config_name = os.environ.get("FLASK_ENV", "production")
app = create_app(config_name)

# Push an application context so tasks can access db, config, etc.
app.app_context().push()
