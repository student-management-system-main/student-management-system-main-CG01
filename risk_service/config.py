"""
risk_service/config.py
----------------------
Configuration class for the AI/ML risk scoring service.

Reads all settings from environment variables so the service can be
configured via a ``.env`` file (loaded by python-dotenv) or injected
directly by Docker Compose / Kubernetes.

Environment variables:
  DB_URL              – SQLAlchemy database URL
                        (e.g. ``mysql+pymysql://user:pass@db:3306/feedb``)
  MODEL_DIR           – Absolute or relative path to the directory where
                        trained model files and ``registry.json`` are stored.
                        Defaults to ``./models``.
  RISK_SERVICE_PORT   – TCP port the Flask dev server listens on.
                        Defaults to ``5001``.

Requirements: 4.1, 4.7, 4.8
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present (no-op when the file does not exist)
load_dotenv()


class Config:
    """Central configuration for the risk scoring service.

    All attributes are read from environment variables at import time so
    that the values are available before the Flask application factory runs.

    Attributes:
        DB_URL: SQLAlchemy-compatible database connection URL.
        MODEL_DIR: Path to the directory containing trained model files and
            ``registry.json``.
        RISK_SERVICE_PORT: Port number the service listens on.
    """

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DB_URL: str = os.environ.get(
        "DB_URL",
        os.environ.get(
            "DATABASE_URL",
            "mysql+pymysql://root:password@localhost:3306/feedb",
        ),
    )

    # ------------------------------------------------------------------
    # Model storage
    # ------------------------------------------------------------------
    MODEL_DIR: Path = Path(
        os.environ.get("MODEL_DIR", str(Path(__file__).parent / "models"))
    )

    # ------------------------------------------------------------------
    # Service networking
    # ------------------------------------------------------------------
    RISK_SERVICE_PORT: int = int(os.environ.get("RISK_SERVICE_PORT", "5001"))
