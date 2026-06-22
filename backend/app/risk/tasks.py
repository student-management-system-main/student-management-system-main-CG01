"""
Celery tasks for risk scoring integration.

Provides:
    - ``risk_score_task(student_id)``     — score a single student via the risk service
    - ``batch_risk_scoring_task()``        — score all students via the risk service batch endpoint

Requirements: 4.2, 4.5, 4.7
"""

import logging

import requests
from celery.exceptions import MaxRetriesExceededError
from flask import current_app

from app import celery

logger = logging.getLogger(__name__)

# Risk category escalation ordering — higher index = higher risk
_CATEGORY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _is_escalation(previous_category: str | None, new_category: str | None) -> bool:
    """Return True if the risk category has escalated (moved to a higher tier)."""
    if previous_category is None or new_category is None:
        return False
    prev_rank = _CATEGORY_ORDER.get(previous_category, -1)
    new_rank = _CATEGORY_ORDER.get(new_category, -1)
    return new_rank > prev_rank


@celery.task(bind=True, max_retries=5)
def risk_score_task(self, student_id: int):
    """
    Compute a risk score for a single student by calling the risk service.

    On a connection error or timeout the task retries up to 5 times with a
    60-second countdown between attempts.  If the service is still unreachable
    after all retries the failure is logged and the task returns without raising
    so that the caller is never blocked.

    When a successful score is received and the student's risk_category has
    *escalated* (low → medium, medium → high, or low → high), an admin
    notification task is enqueued.

    Requirements: 4.2, 4.5
    """
    from app.models.risk_score import RiskScore  # noqa: PLC0415 (avoid circular import at module level)
    from app import db  # noqa: PLC0415

    risk_service_url = current_app.config.get("RISK_SERVICE_URL", "http://risk_service:5001")
    endpoint = f"{risk_service_url}/score"

    try:
        response = requests.post(
            endpoint,
            json={"student_id": student_id},
            timeout=30,
        )
        response.raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning(
            "risk_score_task: risk service unreachable for student %s (attempt %s/%s): %s",
            student_id,
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        try:
            raise self.retry(exc=exc, countdown=60)
        except MaxRetriesExceededError:
            logger.error(
                "risk_score_task: risk service unreachable after %s retries for student %s — giving up.",
                self.max_retries,
                student_id,
            )
            return  # Don't raise — don't block the caller
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "risk_score_task: HTTP error from risk service for student %s: %s",
            student_id,
            exc,
        )
        return

    data = response.json()

    # Determine previous risk category before persisting the new score
    previous_score = (
        db.session.query(RiskScore)
        .filter(RiskScore.student_id == student_id)
        .order_by(RiskScore.computed_at.desc())
        .first()
    )
    previous_category = previous_score.risk_category if previous_score else None
    new_category = data.get("risk_category")

    # Check for escalation and enqueue notification if needed (Requirement 4.5)
    if _is_escalation(previous_category, new_category):
        try:
            from app.notifications.tasks import admin_notification_task  # noqa: PLC0415
            admin_notification_task.delay(student_id=student_id, new_category=new_category)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "risk_score_task: could not enqueue admin_notification_task for student %s: %s",
                student_id,
                exc,
            )

    logger.info(
        "risk_score_task: scored student %s — score=%.2f category=%s version=%s",
        student_id,
        data.get("score", 0),
        new_category,
        data.get("model_version"),
    )


@celery.task
def batch_risk_scoring_task():
    """
    Trigger batch risk scoring for all active students via the risk service.

    Calls ``POST /score/batch`` on the risk service and returns the response
    JSON (e.g., ``{"scored_count": N}``).

    Requirements: 4.7
    """
    risk_service_url = current_app.config.get("RISK_SERVICE_URL", "http://risk_service:5001")
    endpoint = f"{risk_service_url}/score/batch"

    try:
        response = requests.post(endpoint, timeout=300)
        response.raise_for_status()
        result = response.json()
        logger.info("batch_risk_scoring_task: completed — %s", result)
        return result
    except requests.exceptions.RequestException as exc:
        logger.error("batch_risk_scoring_task: failed to reach risk service: %s", exc)
        return {"error": str(exc)}
