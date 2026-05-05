"""FastAPI middleware that extracts optional user from JWT and sets request.state.user_id."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from deeptutor.api.auth_deps import _decode_token


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract JWT user from Authorization header and set request.state.user_id / request.state.user.

    Does NOT block unauthenticated requests - just leaves user_id as None.
    Routes can read request.state.user_id to do per-user isolation.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        user = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            user = _decode_token(auth[7:])

        request.state.user = user
        request.state.user_id = (
            str(user.get("uid", user.get("username"))) if user else None
        )

        response = await call_next(request)
        return response
