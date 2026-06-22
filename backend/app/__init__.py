"""
Application factory for the Fee Management System Flask API.

Usage:
    from app import create_app
    app = create_app("development")   # or "testing" / "production"

The factory pattern keeps the application object out of the global scope,
which makes it straightforward to create multiple instances (e.g., one per
test) and avoids circular-import issues.
"""

import os

from celery import Celery
from flask import Flask, after_this_request, make_response, request
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# ---------------------------------------------------------------------------
# Extension instances (initialised without an app; bound in create_app)
# ---------------------------------------------------------------------------
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
celery = Celery(__name__)


def create_app(config_name: str | None = None) -> Flask:
    """
    Create and configure a Flask application instance.

    Parameters
    ----------
    config_name:
        One of ``"development"``, ``"testing"``, ``"production"``, or
        ``"default"``.  Falls back to the ``FLASK_ENV`` environment variable,
        then to ``"default"`` (which maps to ``DevelopmentConfig``).

    Returns
    -------
    Flask
        A fully configured Flask application ready to serve requests.
    """
    # Resolve config name
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    # Import here to avoid circular imports at module load time
    from config import config_by_name  # noqa: PLC0415

    app = Flask(__name__, instance_relative_config=False)

    # ------------------------------------------------------------------
    # Load configuration
    # ------------------------------------------------------------------
    cfg_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(cfg_class)

    # ------------------------------------------------------------------
    # Initialise extensions
    # ------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Manual CORS handling - handle preflight OPTIONS requests
    @app.before_request
    def handle_options():
        if request.method == "OPTIONS":
            resp = make_response("", 204)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            resp.headers['Access-Control-Max-Age'] = '3600'
            return resp

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '3600'
        return response

    # ------------------------------------------------------------------
    # Configure Celery
    # ------------------------------------------------------------------
    _configure_celery(app)

    # ------------------------------------------------------------------
    # Register JWT error handlers and blocklist loader (Requirement 8.1, 8.5)
    # ------------------------------------------------------------------
    _register_jwt_callbacks(jwt)
    _register_jwt_blocklist_loader(app, jwt)

    # ------------------------------------------------------------------
    # Register blueprints
    # ------------------------------------------------------------------
    _register_blueprints(app)

    # ------------------------------------------------------------------
    # Register global error handlers
    # ------------------------------------------------------------------
    _register_error_handlers(app)

    return app


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _configure_celery(app: Flask) -> None:
    """
    Bind the module-level Celery instance to the Flask app config so that
    tasks can be discovered and executed with the correct broker/backend.

    Also applies the Celery Beat schedule from ``celery_config``, optionally
    overriding the batch-risk-scoring schedule with the ``BATCH_SCORE_CRON``
    app-config value (a 5-field cron expression, e.g. ``"30 1 * * *"``).
    
    For local development, uses in-memory broker and eager task execution
    to avoid Redis dependency.
    """
    import celery_config  # noqa: PLC0415

    # Deep-copy the schedule so we don't mutate the module-level dict
    import copy  # noqa: PLC0415
    schedule = copy.deepcopy(celery_config.beat_schedule)

    # Override the nightly batch-scoring cron if BATCH_SCORE_CRON is configured
    batch_cron: str | None = app.config.get("BATCH_SCORE_CRON")
    if batch_cron:
        try:
            parts = batch_cron.strip().split()
            if len(parts) == 5:
                minute, hour, day_of_month, month_of_year, day_of_week = parts
                from celery.schedules import crontab  # noqa: PLC0415
                schedule["batch-risk-scoring-nightly"]["schedule"] = crontab(
                    minute=minute,
                    hour=hour,
                    day_of_month=day_of_month,
                    month_of_year=month_of_year,
                    day_of_week=day_of_week,
                )
        except Exception as exc:  # noqa: BLE001
            app.logger.warning(
                "_configure_celery: could not parse BATCH_SCORE_CRON=%r: %s — using default.",
                batch_cron,
                exc,
            )

    # For local development, use in-memory broker (memory://) and eager execution
    # to avoid Redis dependency. For production, use Redis.
    flask_env = app.config.get("FLASK_ENV", "production")
    if flask_env in ("local", "development", "testing"):
        # Local/dev: use in-memory broker and eager task execution
        broker_url = "memory://"
        result_backend = "cache+memory://"
        task_always_eager = True
        task_eager_propagates = True
    else:
        # Production: use configured Redis URLs
        broker_url = app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        result_backend = app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
        task_always_eager = app.config.get("CELERY_TASK_ALWAYS_EAGER", False)
        task_eager_propagates = app.config.get("CELERY_TASK_EAGER_PROPAGATES", False)

    celery.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
        task_always_eager=task_always_eager,
        task_eager_propagates=task_eager_propagates,
        beat_schedule=schedule,
        timezone="UTC",
    )

    # Make tasks execute within a Flask application context
    class ContextTask(celery.Task):  # type: ignore[misc]
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask


def _register_blueprints(app: Flask) -> None:
    """Import and register all feature blueprints."""
    # Each blueprint is registered lazily so that the modules are only
    # imported after the app (and its config) is fully set up.

    from app.auth.routes import auth_bp  # noqa: PLC0415
    from app.students.routes import students_bp  # noqa: PLC0415
    from app.fees.routes import fees_bp  # noqa: PLC0415
    from app.invoices.routes import invoices_bp  # noqa: PLC0415
    from app.transactions.routes import transactions_bp  # noqa: PLC0415
    from app.reports.routes import reports_bp  # noqa: PLC0415
    from app.audit.routes import audit_bp  # noqa: PLC0415
    from app.risk.routes import risk_bp  # noqa: PLC0415
    from app.system.routes import system_bp  # noqa: PLC0415
    from app.dashboard.routes import dashboard_bp  # noqa: PLC0415

    api_prefix = "/api/v1"

    app.register_blueprint(auth_bp, url_prefix=f"{api_prefix}/auth")
    app.register_blueprint(students_bp, url_prefix=f"{api_prefix}/students")
    app.register_blueprint(fees_bp, url_prefix=f"{api_prefix}/fee-types")
    app.register_blueprint(invoices_bp, url_prefix=f"{api_prefix}/invoices")
    app.register_blueprint(transactions_bp, url_prefix=f"{api_prefix}/transactions")
    app.register_blueprint(reports_bp, url_prefix=f"{api_prefix}/reports")
    app.register_blueprint(audit_bp, url_prefix=f"{api_prefix}/audit")
    app.register_blueprint(risk_bp, url_prefix=f"{api_prefix}/risk")
    app.register_blueprint(system_bp, url_prefix=f"{api_prefix}/system")
    app.register_blueprint(dashboard_bp, url_prefix=f"{api_prefix}/dashboard")


# ---------------------------------------------------------------------------
# Global JWT blocklist (in-memory, for local development)
# In production, use Redis or implement a database-backed solution
# ---------------------------------------------------------------------------
_jwt_blocklist = set()

# ---------------------------------------------------------------------------
# Global task reminder registry (in-memory, for local development)
# Maps invoice_id -> [task_id1, task_id2, ...] for reminder suppression
# In production, use Redis or implement a database-backed solution
# ---------------------------------------------------------------------------
_task_reminders = {}  # dict mapping invoice_id (int) -> list of task_ids (str)


def _register_jwt_blocklist_loader(app: Flask, jwt_manager: JWTManager) -> None:
    """
    Register a token_in_blocklist_loader that checks an in-memory set for revoked JTIs.
    
    For local development, uses an in-memory set. For production,
    consider using Redis or a database-backed solution.
    """
    @jwt_manager.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload) -> bool:
        jti: str = jwt_payload.get("jti", "")
        if not jti:
            return False
        return jti in _jwt_blocklist


def _register_jwt_callbacks(jwt_manager: JWTManager) -> None:
    """
    Attach custom responses for JWT error conditions so that all auth
    failures return the standard error envelope (Requirement 8.1, 8.5).
    """
    from flask import jsonify  # noqa: PLC0415

    @jwt_manager.unauthorized_loader
    def missing_token_callback(reason: str):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication token is missing or invalid.",
                        "details": {"reason": reason},
                    }
                }
            ),
            401,
        )

    @jwt_manager.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication token has expired.",
                        "details": {},
                    }
                }
            ),
            401,
        )

    @jwt_manager.invalid_token_loader
    def invalid_token_callback(reason: str):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication token is invalid.",
                        "details": {"reason": reason},
                    }
                }
            ),
            401,
        )

    @jwt_manager.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication token has been revoked.",
                        "details": {},
                    }
                }
            ),
            401,
        )


def _register_error_handlers(app: Flask) -> None:
    """
    Register application-wide HTTP error handlers that return the standard
    error envelope instead of Flask's default HTML pages.
    """
    from flask import jsonify  # noqa: PLC0415

    @app.errorhandler(400)
    def bad_request(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": str(exc),
                        "details": {},
                    }
                }
            ),
            400,
        )

    @app.errorhandler(403)
    def forbidden(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to perform this action.",
                        "details": {},
                    }
                }
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "The requested resource was not found.",
                        "details": {},
                    }
                }
            ),
            404,
        )

    @app.errorhandler(409)
    def conflict(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "CONFLICT",
                        "message": str(exc),
                        "details": {},
                    }
                }
            ),
            409,
        )

    @app.errorhandler(422)
    def unprocessable(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "UNPROCESSABLE_ENTITY",
                        "message": str(exc),
                        "details": {},
                    }
                }
            ),
            422,
        )

    @app.errorhandler(500)
    def internal_error(exc):
        # Never expose internal details to the client (Requirement 6.6)
        app.logger.exception("Unhandled server error: %s", exc)
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred. Please try again later.",
                        "details": {},
                    }
                }
            ),
            500,
        )

    @app.errorhandler(503)
    def service_unavailable(exc):
        return (
            jsonify(
                {
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "The service is temporarily unavailable.",
                        "details": {},
                    }
                }
            ),
            503,
        )
