"""
WSGI entry point for the Fee Management System API.

Usage (development):
    flask --app wsgi:app run

Usage (production with Gunicorn):
    gunicorn --bind 0.0.0.0:5000 --workers 4 wsgi:app
"""

import os

from dotenv import load_dotenv, dotenv_values

# Load backend-specific .env file; this is the canonical configuration for
# the Flask API, even when the repository root also contains a separate
# project-level .env file used by Docker or other services.
backend_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(backend_env_path)

# If the Flask CLI or the project root .env file has already set
# FLASK_ENV=development, prefer the backend-local configuration for
# local API development so the app uses the intended sqlite-backed
# LocalConfig instead of the Docker/MySQL development config.
backend_env = dotenv_values(backend_env_path)
if os.environ.get("FLASK_ENV") == "development" and backend_env.get("FLASK_ENV") == "local":
    load_dotenv(backend_env_path, override=True)

from app import create_app

config_name = os.environ.get("FLASK_ENV", "local")
app = create_app(config_name)

if __name__ == "__main__":
    app.run()
