import hashlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import Base
from app.models.entities import User
from app.services.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing() -> None:
    password = "Secret123"
    hashed = hash_password(password)
    # bcrypt hashes start with $2b$ (or $2a$/$2y$ depending on the library
    # version) — never the old unsalted "sha256$..." scheme.
    assert hashed.startswith("$2")
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_rejects_legacy_sha256_hash() -> None:
    # A hash still in the pre-bcrypt format must not verify against
    # anything — it's not a valid bcrypt hash, so this is the expected
    # "needs a password reset" outcome, not a crash.
    import hashlib

    legacy_hash = "sha256$" + hashlib.sha256(b"Secret123").hexdigest()
    assert not verify_password("Secret123", legacy_hash)


def test_create_and_decode_token() -> None:
    token = create_access_token(1, "admin")
    payload = decode_access_token(token)
    assert payload["user_id"] == 1
    assert payload["role"] == "admin"


def test_token_is_a_standard_jwt() -> None:
    # Real JWTs are three base64url segments (header.payload.signature) and
    # decode (without verification) to the standard sub/iat/exp claims plus
    # our custom role claim — this is what distinguishes the new format from
    # the old hand-rolled "user_id:role:expiry:signature" scheme.
    token = create_access_token(1, "admin")
    assert token.count(".") == 2
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert unverified["sub"] == "1"
    assert unverified["role"] == "admin"
    assert "iat" in unverified
    assert "exp" in unverified


def test_decode_expired_token_raises() -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "admin",
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    with pytest.raises(Exception, match="expired"):
        decode_access_token(token)


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(Exception, match="Invalid token"):
        decode_access_token("not_a_valid_token")


def test_decode_legacy_format_token_rejected() -> None:
    # Tokens issued by the pre-upgrade custom "user_id:role:expiry:signature"
    # scheme must be cleanly rejected (not crash) so an old session simply
    # forces a fresh login instead of erroring out.
    expiry = int((datetime.now(UTC) + timedelta(minutes=10)).timestamp())
    legacy_payload = f"1:admin:{settings.secret_key}:{expiry}"
    signature = hashlib.sha256(legacy_payload.encode()).hexdigest()[:16]
    legacy_token = f"1:admin:{expiry}:{signature}"
    with pytest.raises(Exception, match="Invalid token"):
        decode_access_token(legacy_token)