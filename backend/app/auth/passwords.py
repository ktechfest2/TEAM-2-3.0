"""Password hashing with scrypt from the standard library.

Stored form: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``. Parameters are stored with
each hash so they can be raised later without invalidating existing passwords."""

import base64
import hashlib
import hmac
import secrets

N = 2**15
R = 8
P = 1
KEY_BYTES = 64
MAX_MEMORY = 128 * 1024 * 1024

MIN_LENGTH = 10
MAX_LENGTH = 256


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=MAX_MEMORY
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Spent on unknown accounts so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str, email: str | None = None) -> str | None:
    """A reason the password is not acceptable, or None."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    if password.strip() != password or not password.strip():
        return "Do not start or end the password with spaces."
    if len(set(password)) < 5:
        return "Use a less repetitive password."
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) > 3:
        return "Do not include your email name in the password."
    return None


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)
