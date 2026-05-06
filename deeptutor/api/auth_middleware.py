"""FastAPI middleware: extract JWT user and enforce authentication.

- Sets request.state.user and request.state.user_id for all requests.
- Returns 401 for non-authenticated requests on protected routes.
- Allows unauthenticated access to /api/auth/*, /docs, /openapi.json, and health checks.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from deeptutor.api.auth_deps import _decode_token

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/api/auth/login",
    "/api/auth/register",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PREFIXES = (
    "/api/auth/",
    "/_next/",
    "/favicon",
    "/apple-touch",
    "/icon-",
    "/intellitutor-",
    "/logo",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract JWT user and optionally enforce authentication."""

    async def dispatch(self, request: Request, call_next) -> Response:
        user = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            user = _decode_token(auth[7:])

        request.state.user = user
        request.state.user_id = (
            str(user.get("uid", user.get("username"))) if user else None
        )

        # Check if this path requires auth
        path = request.url.path
        is_public = (
            path in PUBLIC_PATHS
            or any(path.startswith(p) for p in PUBLIC_PREFIXES)
            or path.startswith("/api/auth")
        )

        # WebSocket connections skip auth check (handled in route)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # If not public and no user, return 401
        if not is_public and not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Please log in."}
            )

        return await call_next(request)
