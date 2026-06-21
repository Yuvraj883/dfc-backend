import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_signed_guest_token(order_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"order_id": order_id, "exp": expire, "type": "guest_order"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_reservation_cancel_token(reservation_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {"reservation_id": reservation_id, "exp": expire, "type": "reservation_cancel"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_guest_order_token(token: str, order_id: str) -> bool:
    payload = decode_token(token)
    return bool(payload and payload.get("type") == "guest_order" and payload.get("order_id") == order_id)


def verify_reservation_cancel_token(token: str, reservation_id: str) -> bool:
    payload = decode_token(token)
    return bool(
        payload
        and payload.get("type") == "reservation_cancel"
        and payload.get("reservation_id") == reservation_id
    )
