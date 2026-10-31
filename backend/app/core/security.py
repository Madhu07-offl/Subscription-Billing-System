import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings
from app.core.errors import AppError

MAX_PASSWORD_BYTES = 72  # bcrypt ignores (or rejects) anything beyond this


def password_problems(password: str) -> list[str]:
    """Password rule from the contract: more than 8 characters, upper, lower and a special character."""
    problems = []
    if len(password) < 9:
        problems.append("Needs more than 8 characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        problems.append("Must be at most 72 bytes long")
    if not re.search(r"[a-z]", password):
        problems.append("Needs a lowercase letter")
    if not re.search(r"[A-Z]", password):
        problems.append("Needs an uppercase letter")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("Needs a special character")
    return problems


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Works for hashes from pgcrypto crypt(..., gen_salt('bf')) ($2a$) as well as bcrypt ($2b$)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # over-long password or malformed hash
        return False


# A real hash to compare against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """Returns (jwt, expires_in_seconds)."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=s.jwt_expires_seconds),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), s.jwt_expires_seconds


def decode_access_token(token: str) -> uuid.UUID:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise AppError.unauthenticated("Invalid or expired token") from None


def new_reset_token() -> tuple[str, str]:
    """Returns (raw_token_for_the_link, sha256_hex_to_store). Only the hash is kept in the DB."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
