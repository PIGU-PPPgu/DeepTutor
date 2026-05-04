"""User registration, login, and minimal admin user management with JWT auth."""

import os
import time
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.hash import bcrypt
from pydantic import BaseModel

router = APIRouter()

DB_PATH = os.path.expanduser("~/.intellitutor/users.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "intellitutor-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES = 86400 * 7  # 7 days
INVITE_CODE = os.environ.get("INTELLITUTOR_INVITE_CODE") or os.environ.get("INVITE_CODE")
INVITE_LIMIT = int(os.environ.get("INTELLITUTOR_INVITE_LIMIT") or os.environ.get("INVITE_LIMIT") or "0")
ADMIN_USERNAME = os.environ.get("INTELLITUTOR_ADMIN_USERNAME", "pigouwu")


class AdminUserUpdate(BaseModel):
    display_name: str | None = None
    is_admin: bool | None = None
    is_disabled: bool | None = None


class AdminPasswordReset(BaseModel):
    password: str


async def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute(
"""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            invite_code TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    # Existing deployments may have been created before invite/admin fields existed.
    cols = await db.execute_fetchall("PRAGMA table_info(users)")
    col_names = {c[1] for c in cols}
    if "invite_code" not in col_names:
        await db.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    if "is_admin" not in col_names:
        await db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "is_disabled" not in col_names:
        await db.execute("ALTER TABLE users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0")
    if ADMIN_USERNAME:
        await db.execute("UPDATE users SET is_admin = 1, is_disabled = 0 WHERE username = ?", (ADMIN_USERNAME,))
    await db.commit()
    return db


def make_token(user_id: int, username: str, display_name: str, is_admin: bool = False) -> str:
    payload = {
        "sub": str(user_id),
        "uid": user_id,
        "username": username,
        "display_name": display_name,
        "is_admin": bool(is_admin),
        "exp": int(time.time()) + JWT_EXPIRES,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    return payload


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin permission required")
    return user


def _public_user(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "invite_code": row["invite_code"],
        "is_admin": bool(row["is_admin"]),
        "is_disabled": bool(row["is_disabled"]),
        "created_at": row["created_at"],
    }


@router.post("/api/auth/register")
async def register(body: dict):
    username = body.get("username", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", username).strip()
    invite_code = body.get("invite_code", "")

    if INVITE_CODE and invite_code != INVITE_CODE:
        raise HTTPException(403, "邀请码无效或已过期")

    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if len(username) < 2:
        raise HTTPException(400, "Username too short (min 2 chars)")
    if len(password) < 4:
        raise HTTPException(400, "Password too short (min 4 chars)")

    db = await get_db()
    try:
        existing = await db.execute_fetchall(
            "SELECT id FROM users WHERE username = ?", (username,)
        )
        if existing:
            raise HTTPException(409, "Username already taken")

        if INVITE_CODE and INVITE_LIMIT > 0:
            rows = await db.execute_fetchall(
                "SELECT COUNT(*) AS count FROM users WHERE invite_code = ?", (invite_code,)
            )
            if int(rows[0]["count"]) >= INVITE_LIMIT:
                raise HTTPException(403, "邀请码名额已满")

        pw_hash = bcrypt.hash(password)
        now = datetime.now(timezone.utc).isoformat()
        is_admin = 1 if ADMIN_USERNAME and username == ADMIN_USERNAME else 0
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash, display_name, invite_code, is_admin, is_disabled, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (username, pw_hash, display_name, invite_code if INVITE_CODE else None, is_admin, now),
        )
        await db.commit()
        user_id = cursor.lastrowid
    finally:
        await db.close()

    token = make_token(user_id, username, display_name, bool(is_admin))
    return {"token": token, "user": {"id": user_id, "username": username, "display_name": display_name, "is_admin": bool(is_admin)}}


@router.post("/api/auth/login")
async def login(body: dict):
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(400, "Username and password required")

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id, username, password_hash, display_name, is_admin, is_disabled FROM users WHERE username = ?",
            (username,),
        )
    finally:
        await db.close()

    if not rows:
        raise HTTPException(401, "Invalid username or password")

    row = rows[0]
    if row["is_disabled"]:
        raise HTTPException(403, "This account has been disabled")
    if not bcrypt.verify(password, row["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    token = make_token(row["id"], row["username"], row["display_name"], bool(row["is_admin"]))
    return {
        "token": token,
        "user": {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "is_admin": bool(row["is_admin"])},
    }


@router.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": {"id": user.get("uid") or user["sub"], "username": user["username"], "display_name": user["display_name"], "is_admin": bool(user.get("is_admin"))}}


@router.get("/api/admin/users")
async def admin_list_users(_admin: dict = Depends(get_current_admin)):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id, username, display_name, invite_code, is_admin, is_disabled, created_at FROM users ORDER BY created_at DESC"
        )
        invite_rows = await db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM users WHERE invite_code = ?", (INVITE_CODE or "",)
        )
    finally:
        await db.close()
    return {
        "users": [_public_user(row) for row in rows],
        "invite": {
            "enabled": bool(INVITE_CODE),
            "code": INVITE_CODE,
            "limit": INVITE_LIMIT,
            "used": int(invite_rows[0]["count"]) if INVITE_CODE else 0,
        },
    }


@router.patch("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, body: AdminUserUpdate, admin: dict = Depends(get_current_admin)):
    if user_id == int(admin["sub"]) and body.is_disabled is True:
        raise HTTPException(400, "You cannot disable your own admin account")

    updates: list[str] = []
    values: list[object] = []
    if body.display_name is not None:
        display_name = body.display_name.strip()
        if not display_name:
            raise HTTPException(400, "Display name cannot be empty")
        updates.append("display_name = ?")
        values.append(display_name)
    if body.is_admin is not None:
        updates.append("is_admin = ?")
        values.append(1 if body.is_admin else 0)
    if body.is_disabled is not None:
        updates.append("is_disabled = ?")
        values.append(1 if body.is_disabled else 0)
    if not updates:
        raise HTTPException(400, "No changes provided")

    db = await get_db()
    try:
        values.append(user_id)
        cursor = await db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
        if cursor.rowcount == 0:
            raise HTTPException(404, "User not found")
        await db.commit()
    finally:
        await db.close()
    return {"status": "ok"}


@router.post("/api/admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: int, body: AdminPasswordReset, _admin: dict = Depends(get_current_admin)):
    if len(body.password) < 4:
        raise HTTPException(400, "Password too short (min 4 chars)")
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (bcrypt.hash(body.password), user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "User not found")
        await db.commit()
    finally:
        await db.close()
    return {"status": "ok"}
