import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import select

from marketing.config import settings
from marketing.models import AuthSession, User, uid

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash("invalid-login-password")


def register(db, username, password):
    if db.scalar(select(User).where(User.username == username)):
        raise ValueError("用户名已存在")
    user = User(username=username, password_hash=hasher.hash(password), workspace_id=uid())
    db.add(user)
    db.flush()
    return user


def login(db, username, password):
    user = db.scalar(select(User).where(User.username == username))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, password)
    except VerificationError:
        raise HTTPException(401, "用户名或密码错误") from None
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            csrf=csrf,
            expires_at=time.time() + 86400,
        )
    )
    db.flush()
    return user, token, csrf


def authenticate(db, request: Request):
    token = request.cookies.get("marketing_session", "")
    session = db.get(AuthSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at <= time.time():
        raise HTTPException(401, "请登录")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
            raise HTTPException(403, "CSRF 校验失败")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "账号不存在")
    return user, session


def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin != settings.app_origin:
        raise HTTPException(403, "来源不允许")
