"""Password hashing (bcrypt)."""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Return bcrypt hash string for storage in ``password_hash``."""
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(
        plain.encode("utf-8"),
        password_hash.encode("utf-8"),
    )
