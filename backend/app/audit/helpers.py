
"""
Audit log writer helper.

Provides a single utility function ``write_audit_log`` that every mutating
endpoint calls to persist an immutable record of every create, update,
deactivate, and export action in the ``logs`` table.

Requirements: 1.4, 9.1
"""

from app import db
from app.models.log import Log


def write_audit_log(
    actor_id: int | None,
    resource_type: str,
    resource_id: int | None,
    action: str,
    previous_values: dict | None = None,
    new_values: dict | None = None,
) -> Log:
    """
    Insert an append-only audit entry into the ``logs`` table.

    Parameters
    ----------
    actor_id:
        Primary key of the User who performed the action.  ``None`` for
        system-generated / scheduled actions.
    resource_type:
        The type of resource affected (e.g. ``"student"``, ``"invoice"``).
    resource_id:
        Primary key of the affected resource row.
    action:
        Short action label (e.g. ``"create"``, ``"update"``,
        ``"deactivate"``, ``"export"``).
    previous_values:
        Snapshot of the resource's relevant fields *before* the change.
        Pass ``None`` for create actions.
    new_values:
        Snapshot of the resource's relevant fields *after* the change.
        Pass ``None`` for delete / deactivate actions where only previous
        values matter.

    Returns
    -------
    Log
        The newly created (but NOT yet committed) ``Log`` instance.
        The caller must call ``db.session.commit()`` to persist the row.
    """
    entry = Log(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        previous_values=previous_values,
        new_values=new_values,
        # Notification-specific fields — not used for audit log entries
        channel=None,
        delivery_status=None,
    )
    db.session.add(entry)
    # The caller is responsible for the surrounding db.session.commit() call.
    # We do NOT commit here so callers can batch multiple writes atomically.
    return entry
