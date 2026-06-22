"""
Auth blueprint routes.

Implements JWT-based login, token refresh, and logout endpoints.

Requirements: 8.1, 8.4, 8.5
"""

from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_cors import cross_origin
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from app.models.user import User

auth_bp = Blueprint("auth", __name__)


def _error(code: str, message: str, details: dict | None = None, status: int = 400):
    """Return a standard error envelope response."""
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                }
            }
        ),
        status,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

@cross_origin()
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate a user and issue JWT access + refresh tokens.

    Request body (JSON):
        {"username": str, "password": str}

    Returns:
        200: {"data": {"access_token": str, "refresh_token": str, "user": dict}}
        400: VALIDATION_ERROR — missing username or password
        401: INVALID_CREDENTIALS — user not found or wrong password
        403: ACCOUNT_INACTIVE — user account is disabled
    """
    body = request.get_json(silent=True) or {}

    # Validate required fields
    missing = [f for f in ("username", "password") if not body.get(f)]
    if missing:
        return _error(
            "VALIDATION_ERROR",
            "Missing required fields.",
            {"missing_fields": missing},
            400,
        )

    username: str = body["username"]
    password: str = body["password"]

    # Look up user by username or email (allows using email as username)
    user = User.find_by_username(username)
    if user is None and "@" in username:
        user = User.find_by_email(username)

    if user is None or not user.check_password(password):
        return _error(
            "INVALID_CREDENTIALS",
            "Invalid username or password.",
            {},
            401,
        )

    # Check account status
    if not user.is_active:
        return _error(
            "ACCOUNT_INACTIVE",
            "This account has been deactivated. Please contact an administrator.",
            {},
            403,
        )

    # Issue tokens (Requirement 8.4: 8h access, 7d refresh)
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role},
        expires_delta=timedelta(
            seconds=current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 8 * 3600)
        ),
    )
    refresh_token = create_refresh_token(
        identity=str(user.id),
        expires_delta=timedelta(
            seconds=current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES", 7 * 24 * 3600)
        ),
    )

    return (
        jsonify(
            {
                "data": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "user": user.to_dict(),
                }
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Issue a new access token using a valid refresh token.

    Returns:
        200: {"data": {"access_token": str}}
    """
    identity = get_jwt_identity()
    new_access_token = create_access_token(
        identity=identity,
        expires_delta=timedelta(
            seconds=current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 8 * 3600)
        ),
    )
    return jsonify({"data": {"access_token": new_access_token}}), 200


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------

@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """
    Revoke the current access token by adding its JTI to the in-memory blocklist.

    Returns:
        200: {"data": {"message": "Successfully logged out"}}
    """
    from app import _jwt_blocklist  # noqa: PLC0415

    jwt_payload = get_jwt()
    jti: str = jwt_payload["jti"]

    # Add JTI to the in-memory blocklist
    _jwt_blocklist.add(jti)

    return jsonify({"data": {"message": "Successfully logged out"}}), 200
