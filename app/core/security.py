import re
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request

from app.core.config import get_settings

_hasher = PasswordHasher()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerificationError:
        return False


class RateLimiter:
    """Sliding-window limiter, in memory. Fine for one process; use Redis behind many."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
        q.append(now)

    def reset(self) -> None:
        self.hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Deliberately ignores X-Forwarded-For: it is client-controlled unless a trusted proxy sets it.
    return request.client.host if request.client else "unknown"


def rate_limit_general(request: Request) -> None:
    s = get_settings()
    limiter.check(f"ip:{client_ip(request)}", s.rate_limit_ip_per_minute)
    uid = request.session.get("uid")
    if uid:
        limiter.check(f"user:{uid}", s.rate_limit_user_per_minute)


def rate_limit_scan(request: Request) -> None:
    limiter.check(f"scan:{client_ip(request)}", get_settings().scan_limit_ip_per_minute)
