"""User registration and login with JWT auth."""

import os
import time
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.hash import bcrypt

router = APIRouter()

DB_PATH = os.path.expanduser("~/.intellitutor/users.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "intellitutor-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES = 86400 * 7  # 7 days
INVITE_CODE = os.environ.get("INTELLITUTOR_INVITE_CODE") or os.environ.get("INVITE_CODE")
INVITE_LIMIT = int(os.environ.get("INTELLITUTOR_INVITE_LIMIT") or os.environ.get("INVITE_LIMIT") or "0")


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
            created_at TEXT NOT NULL
        )"""
    )
    # Existing deployments may have been created before invite_code existed.
    cols = await db.execute_fetchall("PRAGMA table_info(users)")
    if "invite_code" not in {c[1] for c in cols}:
        await db.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    await db.commit()
    return db


def make_token(user_id: int, username: str, display_name: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "display_name": display_name,
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
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash, display_name, invite_code, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, pw_hash, display_name, invite_code if INVITE_CODE else None, now),
        )
        await db.commit()
        user_id = cursor.lastrowid
    finally:
        await db.close()

    token = make_token(user_id, username, display_name)
    return {"token": token, "user": {"id": user_id, "username": username, "display_name": display_name}}


@router.post("/api/auth/login")
async def login(body: dict):
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(400, "Username and password required")

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id, username, password_hash, display_name FROM users WHERE username = ?",
            (username,),
        )
    finally:
        await db.close()

    if not rows:
        raise HTTPException(401, "Invalid username or password")

    row = rows[0]
    if not bcrypt.verify(password, row["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    token = make_token(row["id"], row["username"], row["display_name"])
    return {
        "token": token,
        "user": {"id": row["id"], "username": row["username"], "display_name": row["display_name"]},
    }


@router.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": {"id": user["sub"], "username": user["username"], "display_name": user["display_name"]}}
