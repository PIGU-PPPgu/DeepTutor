"""Authentication dependencies for FastAPI routes.

Provides three levels:
- get_optional_user: returns user dict or None (no auth required)
- get_current_user: requires valid JWT, raises 401 if missing
- get_current_admin: requires valid JWT + admin role, raises 403
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError

JWT_SECRET = os.environ.get("JWT_SECRET", "intellitutor-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"


def _decode_token(token: str) -> dict | None:
    """Decode a JWT token, return payload or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (JWTError, Exception):
        return None


async def get_optional_user(request: Request) -> dict | None:
    """Extract user from JWT if present, otherwise return None.
    Does NOT raise - safe for routes that work with or without auth."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        user = _decode_token(auth[7:])
        if user and not user.get("is_disabled"):
            return user
    return None


async def get_current_user(request: Request) -> dict:
    """Require valid JWT. Raises 401 if missing or invalid."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    user = _decode_token(auth[7:])
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    if user.get("is_disabled"):
        raise HTTPException(403, "Account disabled")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require valid JWT + admin role. Raises 403 if not admin."""
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin permission required")
    return user
