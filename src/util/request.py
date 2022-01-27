import functools
from typing import List
from flask_jwt_extended import get_jwt_identity, jwt_required
from util.response import create_error_response


def require_roles(roles: List[str]):
    """
    This decorator takes a list of valid roles and checks to see if the
    current user accessing the decorated route has one of those roles.
    If not, this function returns a 403 JSON forbidden response.
    """
    VALID_ROLES = {"user", "admin", "super"}

    def decorator(func):
        @functools.wraps(func)
        @jwt_required()
        def wrapper(*args, **kwargs):
            for role in roles:
                if role.lower() not in VALID_ROLES:
                    raise ValueError(
                        f"Role must one of {', '.join(VALID_ROLES)}, got {role}"
                    )

            current_user = get_jwt_identity()

            if not current_user:
                return create_error_response(
                    "You must be logged in to access this resource", 403
                )

            if not current_user["role"]:
                raise KeyError("'role' missing from the JWT, did you forget to set it?")

            if current_user["role"].lower() not in roles:
                return create_error_response(
                    "You don't have permission to view this resource", 403
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator
