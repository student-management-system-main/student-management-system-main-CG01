"""
JWT middleware helpers and role-based access decorators.

Provides:
    - ``@admin_required``            — JWT-protected, admin role only (403 otherwise)
    - ``@viewer_or_admin_required``  — JWT-protected, any authenticated user
    - ``get_current_user_role()``    — read the ``role`` claim from the active JWT
    - ``get_current_user_id()``      — read the user identity from the active JWT

Requirements: 8.1, 8.2, 8.3
"""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_user_role() -> str:
    """
    Return the ``role`` claim from the currently active JWT.

    Must be called inside a request context where a valid JWT has already
    been verified (i.e., inside a view decorated with ``@jwt_required()``
    or one of the decorators below).

    Returns
    -------
    str
        The role string stored in the JWT claims (e.g. ``"admin"`` or
        ``"viewer"``).
    """
    claims = get_jwt()
    return claims.get("role", "")


def get_current_user_id() -> int:
    """
    Return the user ID from the currently active JWT identity.

    The identity is stored as a string (see ``auth/routes.py`` where
    ``identity=str(user.id)`` is passed to ``create_access_token``), so
    this helper converts it back to ``int`` for convenience.

    Returns
    -------
    int
        The authenticated user's primary-key ID.
    """
    return int(get_jwt_identity())


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def admin_required(fn):
    """
    Decorator that requires a valid JWT **and** an ``admin`` role.

    Behaviour
    ---------
    1. Validates the JWT via ``@jwt_required()`` — missing / expired / invalid
       tokens are rejected with 401 by Flask-JWT-Extended's error handlers
       (registered in ``app/__init__.py``).
    2. Reads the ``role`` claim from the verified JWT.
    3. If the role is not ``"admin"``, returns a 403 error envelope.
    4. Otherwise, calls the wrapped view function normally.

    Example
    -------
    ::

        @fees_bp.route("/", methods=["POST"])
        @admin_required
        def create_fee_type():
            ...

    Requirements: 8.2, 8.3
    """
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        role = get_current_user_role()
        if role != "admin":
            return (
                jsonify(
                    {
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "Admin access required.",
                            "details": {},
                        }
                    }
                ),
                403,
            )
        return fn(*args, **kwargs)

    return wrapper


def viewer_or_admin_required(fn):
    """
    Decorator that requires a valid JWT for any authenticated user.

    This is a semantic alias for ``@jwt_required()`` that makes the intent
    explicit at the route level — any user with a valid token (regardless of
    role) may access the endpoint.

    Example
    -------
    ::

        @students_bp.route("/", methods=["GET"])
        @viewer_or_admin_required
        def list_students():
            ...

    Requirements: 8.2
    """
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper
