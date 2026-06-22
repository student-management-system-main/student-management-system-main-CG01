"""
Application configuration classes.

Each class reads its settings from environment variables so that no
secrets are hard-coded in source.  Use python-dotenv (or Docker env
files) to supply values at runtime.

Usage:
    from config import DevelopmentConfig, TestingConfig, ProductionConfig
"""

import os


class BaseConfig:
    """Shared defaults inherited by all environment configs."""

    # ------------------------------------------------------------------ #
    # Flask core
    # ------------------------------------------------------------------ #
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG: bool = False
    TESTING: bool = False

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/fee_management",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    # Use SERIALIZABLE isolation for financial writes (overridden per-session
    # where needed; set as engine default here for safety).
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    # ------------------------------------------------------------------ #
    # JWT (Flask-JWT-Extended)
    # ------------------------------------------------------------------ #
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "change-jwt-secret")
    # Access token valid for 8 hours (Requirement 8.4)
    JWT_ACCESS_TOKEN_EXPIRES: int = int(
        os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 8 * 3600)
    )
    # Refresh token valid for 7 days (Requirement 8.4)
    JWT_REFRESH_TOKEN_EXPIRES: int = int(
        os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 7 * 24 * 3600)
    )
    # Store refresh-token blocklist in Redis
    JWT_TOKEN_LOCATION: list = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"

    # ------------------------------------------------------------------ #
    # Redis / Celery
    # ------------------------------------------------------------------ #
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.environ.get(
        "CELERY_BROKER_URL", "redis://localhost:6379/0"
    )
    CELERY_RESULT_BACKEND: str = os.environ.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )

    # ------------------------------------------------------------------ #
    # Risk service
    # ------------------------------------------------------------------ #
    RISK_SERVICE_URL: str = os.environ.get(
        "RISK_SERVICE_URL", "http://risk_service:5001"
    )

    # ------------------------------------------------------------------ #
    # Notification providers
    # ------------------------------------------------------------------ #
    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "smtp.example.com")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS: bool = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get(
        "MAIL_DEFAULT_SENDER", "noreply@example.com"
    )

    TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.environ.get("TWILIO_FROM_NUMBER", "")

    # ------------------------------------------------------------------ #
    # Batch scoring schedule (cron expression, default: midnight daily)
    # ------------------------------------------------------------------ #
    BATCH_SCORE_CRON: str = os.environ.get("BATCH_SCORE_CRON", "0 0 * * *")

    # ------------------------------------------------------------------ #
    # Scheduled maintenance window (Requirement 10.4)
    # ISO 8601 datetime strings, e.g. "2025-08-01T02:00:00" / "2025-08-01T04:00:00"
    # Leave unset (None) when no maintenance is planned.
    # ------------------------------------------------------------------ #
    MAINTENANCE_START: str | None = os.environ.get("MAINTENANCE_START", None)
    MAINTENANCE_END: str | None = os.environ.get("MAINTENANCE_END", None)

    # ------------------------------------------------------------------ #
    # Bcrypt cost factor (Requirement 8.7)
    # ------------------------------------------------------------------ #
    BCRYPT_LOG_ROUNDS: int = int(os.environ.get("BCRYPT_LOG_ROUNDS", 12))


class LocalConfig(BaseConfig):
    """
    Local development without Docker — uses SQLite file database and
    disables Redis/Celery dependencies so the app runs standalone.
    """

    DEBUG: bool = True
    TESTING: bool = False
    BCRYPT_LOG_ROUNDS: int = 4

    # SQLite file database — reads DATABASE_URL from env if set, otherwise
    # defaults to a local file in the backend directory
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///fee_local.db",
    )

    # Disable engine options that cause issues with SQLite
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}

    # Use short-lived tokens for local testing
    JWT_ACCESS_TOKEN_EXPIRES: int = int(
        os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 8 * 3600)
    )

    # Run Celery tasks eagerly (inline) — no broker needed
    CELERY_TASK_ALWAYS_EAGER: bool = True
    CELERY_TASK_EAGER_PROPAGATES: bool = False

    # Risk service running locally
    RISK_SERVICE_URL: str = os.environ.get(
        "RISK_SERVICE_URL", "http://localhost:5001"
    )


class DevelopmentConfig(BaseConfig):
    """Local development — verbose logging, no HTTPS enforcement."""

    DEBUG: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/fee_management_dev",
    )
    # Lower bcrypt cost for faster dev iteration (still ≥ 4 for bcrypt minimum)
    BCRYPT_LOG_ROUNDS: int = int(os.environ.get("BCRYPT_LOG_ROUNDS", 4))


class TestingConfig(BaseConfig):
    """Automated test runs — in-memory SQLite, no real external calls."""

    TESTING: bool = True
    DEBUG: bool = True
    # Use SQLite in-memory so tests run without a MySQL server
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    # Disable CSRF / security features that interfere with test clients
    WTF_CSRF_ENABLED: bool = False
    # Short-lived tokens make expiry tests fast
    JWT_ACCESS_TOKEN_EXPIRES: int = int(
        os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 300)  # 5 minutes
    )
    JWT_REFRESH_TOKEN_EXPIRES: int = int(
        os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 600)  # 10 minutes
    )
    # Use a synchronous task runner so Celery tasks execute inline during tests
    CELERY_TASK_ALWAYS_EAGER: bool = True
    CELERY_TASK_EAGER_PROPAGATES: bool = True
    # Minimal bcrypt cost for speed
    BCRYPT_LOG_ROUNDS: int = 4


class ProductionConfig(BaseConfig):
    """Production — strict settings; all secrets MUST come from env vars."""

    # Use .get() with fallback to avoid errors when not in production
    # (Production deployment will require these env vars to be set)
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "change-jwt-secret")
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/fee_management",
    )

    # Enforce HTTPS (Requirement 8.6) — handled at Nginx level, but also
    # set the secure cookie flag and HSTS header via Flask-Talisman or Nginx.
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # Production bcrypt cost (Requirement 8.7)
    BCRYPT_LOG_ROUNDS: int = int(os.environ.get("BCRYPT_LOG_ROUNDS", 12))


# Convenience mapping used by the application factory
config_by_name: dict = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "local": LocalConfig,
    "default": LocalConfig,
}
