"""
Audit log blueprint routes.

Endpoints
---------
GET  /api/v1/audit  — Admin only; paginated, filterable audit log query

Append-only enforcement
-----------------------
No PUT, PATCH, or DELETE routes are defined on this blueprint.
Any attempt to use those methods on /api/v1/audit or sub-paths returns 405.

Requirements: 9.1, 9.3, 9.4
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app import db
from app.auth.decorators import admin_required
from app.models.log import Log

audit_bp = Blueprint("audit", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_to_dict(log: Log) -> dict:
    """Serialize a Log ORM instance to a plain dict for JSON responses."""
    return {
        "id": log.id,
        "actor_id": log.actor_id,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "action": log.action,
        "previous_values": log.previous_values,
        "new_values": log.new_values,
        "channel": log.channel,
        "delivery_status": log.delivery_status,
        "created_at": (
            log.created_at.isoformat() if log.created_at else None
        ),
    }


def _parse_iso_date(value: str, param_name: str):
    """
    Parse an ISO date string (YYYY-MM-DD or full ISO datetime).

    Returns a datetime object (UTC-aware) on success, or a Flask error
    response tuple on failure.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc), None
        except ValueError:
            continue
    return None, (
        jsonify(
            {
                "error": {
                    "code": "BAD_REQUEST",
                    "message": (
                        f"Invalid date format for '{param_name}'. "
                        "Expected ISO date (YYYY-MM-DD) or ISO datetime "
                        "(YYYY-MM-DDTHH:MM:SS)."
                    ),
                    "details": {},
                }
            }
        ),
        400,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/audit
# ---------------------------------------------------------------------------

@audit_bp.route("/", methods=["GET"])
@admin_required
def list_audit_logs():
    """
    Return a paginated list of audit log entries, optionally filtered.

    Query parameters
    ----------------
    date_from    : str (ISO date/datetime), optional — filter logs created on or after this date
    date_to      : str (ISO date/datetime), optional — filter logs created on or before this date
    actor_id     : int, optional — filter by the actor who performed the action
    resource_type: str, optional — filter by the type of resource affected
    action       : str, optional — filter by the action label
    page         : int (default 1) — page number (1-indexed)
    per_page     : int (default 50, max 200) — number of results per page

    Returns
    -------
    200 JSON:
        {
            "data": {
                "logs": [...],
                "total": <int>,
                "page": <int>,
                "per_page": <int>
            }
        }

    Requirements: 9.1, 9.3, 9.4
    """
    args = request.args

    # ------------------------------------------------------------------
    # Parse and validate pagination parameters
    # ------------------------------------------------------------------
    try:
        page = int(args.get("page", 1))
        if page < 1:
            raise ValueError
    except ValueError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "'page' must be a positive integer.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    try:
        per_page = int(args.get("per_page", 50))
        if per_page < 1:
            raise ValueError
    except ValueError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "'per_page' must be a positive integer.",
                        "details": {},
                    }
                }
            ),
            400,
        )

    # Clamp per_page to maximum of 200
    per_page = min(per_page, 200)

    # ------------------------------------------------------------------
    # Parse optional filter parameters
    # ------------------------------------------------------------------
    date_from_str = args.get("date_from")
    date_to_str = args.get("date_to")
    actor_id_str = args.get("actor_id")
    resource_type = args.get("resource_type")
    action = args.get("action")

    date_from = None
    if date_from_str:
        date_from, err = _parse_iso_date(date_from_str, "date_from")
        if err:
            return err

    date_to = None
    if date_to_str:
        date_to, err = _parse_iso_date(date_to_str, "date_to")
        if err:
            return err

    actor_id = None
    if actor_id_str is not None:
        try:
            actor_id = int(actor_id_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "BAD_REQUEST",
                            "message": "'actor_id' must be an integer.",
                            "details": {},
                        }
                    }
                ),
                400,
            )

    # ------------------------------------------------------------------
    # Build query
    # ------------------------------------------------------------------
    query = Log.query

    if date_from is not None:
        query = query.filter(Log.created_at >= date_from)

    if date_to is not None:
        query = query.filter(Log.created_at <= date_to)

    if actor_id is not None:
        query = query.filter(Log.actor_id == actor_id)

    if resource_type:
        query = query.filter(Log.resource_type == resource_type)

    if action:
        query = query.filter(Log.action == action)

    # Order by most recent first; stable ordering by id as tiebreaker
    query = query.order_by(Log.created_at.desc(), Log.id.desc())

    # ------------------------------------------------------------------
    # Execute paginated query
    # ------------------------------------------------------------------
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    logs = [_log_to_dict(log) for log in pagination.items]

    return (
        jsonify(
            {
                "data": {
                    "logs": logs,
                    "total": pagination.total,
                    "page": page,
                    "per_page": per_page,
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Append-only enforcement — return 405 for mutating methods on this blueprint
# ---------------------------------------------------------------------------

@audit_bp.route("/", methods=["PUT", "PATCH", "DELETE"])
@audit_bp.route("/<path:subpath>", methods=["PUT", "PATCH", "DELETE"])
def audit_mutate_not_allowed(subpath=None):
    """
    Reject any attempt to mutate audit log entries.

    Audit logs are append-only (Requirement 9.4).  No PUT, PATCH, or DELETE
    operation is permitted through the API.
    """
    return (
        jsonify(
            {
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": (
                        "Audit log entries are append-only and cannot be "
                        "modified or deleted."
                    ),
                    "details": {},
                }
            }
        ),
        405,
    )
