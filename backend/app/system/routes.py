"""
System / operational endpoints.

Provides:
    GET /api/v1/system/maintenance  — no authentication required (Requirement 10.4)
    GET /api/v1/system/health       — DB + Redis liveness check (Requirements 15.1, 15.2)

Env vars consumed (via app.config):
    MAINTENANCE_START   ISO 8601 datetime string, e.g. "2025-08-01T02:00:00"
    MAINTENANCE_END     ISO 8601 datetime string, e.g. "2025-08-01T04:00:00"
    REDIS_URL           Redis connection URL

Requirements: 10.4, 15.1, 15.2
"""

import logging

from flask import Blueprint, current_app, jsonify

logger = logging.getLogger(__name__)

system_bp = Blueprint("system", __name__)


@system_bp.get("/maintenance")
def get_maintenance():
    """
    Return the scheduled maintenance window.

    Response body examples
    ----------------------
    No maintenance scheduled::

        {"data": {"maintenance": null}}

    Maintenance window configured::

        {
            "data": {
                "maintenance": {
                    "start": "2025-08-01T02:00:00",
                    "end":   "2025-08-01T04:00:00",
                    "message": "Scheduled maintenance"
                }
            }
        }
    """
    start: str | None = current_app.config.get("MAINTENANCE_START")
    end: str | None = current_app.config.get("MAINTENANCE_END")

    if start and end:
        maintenance = {
            "start": start,
            "end": end,
            "message": "Scheduled maintenance",
        }
    else:
        maintenance = None

    return jsonify({"data": {"maintenance": maintenance}}), 200


# ---------------------------------------------------------------------------
# GET /api/v1/system/health
# ---------------------------------------------------------------------------

@system_bp.get("/health")
def health_check():
    """
    Liveness check endpoint.

    Verifies that the database is reachable. Redis is optional for local
    development (uses in-memory Celery broker).

    Returns
    -------
    200  {"status": "ok", "dependencies": {"database": true}}
         Database is healthy.
    503  {"status": "down", "dependencies": {"database": false}}
         Database is unavailable (critical).

    Requirements: 15.1, 15.2
    """
    from sqlalchemy import text  # noqa: PLC0415
    from app import db  # noqa: PLC0415

    db_ok = False

    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.error("health_check: database unreachable: %s", exc)

    if db_ok:
        return jsonify({"status": "ok", "dependencies": {"database": True}}), 200

    return (
        jsonify(
            {
                "status": "down",
                "dependencies": {
                    "database": False,
                },
            }
        ),
        503,
    )
