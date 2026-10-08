"""
Unit tests for the startup bootstrap's course grader account.

No Docker stack required: the database session is replaced by a fake.

Run with:
    cd tests/unit && pytest test_bootstrap.py -v
"""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import bootstrap
from app.services.auth_service import hash_password, verify_password


def encoded_hash(password: str) -> str:
    return base64.b64encode(hash_password(password).encode()).decode()


def fake_session(existing):
    """An AsyncSessionLocal stand-in whose one query returns `existing`."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, db


def test_grader_hash_decodes_to_a_usable_bcrypt_hash():
    with patch.object(bootstrap.settings, "GRADER_PASSWORD_HASH", encoded_hash("s3cret-pass")):
        decoded = bootstrap.grader_password_hash()
    assert decoded is not None and verify_password("s3cret-pass", decoded)


def test_unset_or_malformed_grader_hash_is_ignored():
    for value in ("", "not base64 !!", base64.b64encode(b"plain text").decode()):
        with patch.object(bootstrap.settings, "GRADER_PASSWORD_HASH", value):
            assert bootstrap.grader_password_hash() is None


async def test_grader_account_is_created_as_admin():
    factory, db = fake_session(existing=None)
    with patch.object(bootstrap, "AsyncSessionLocal", factory):
        await bootstrap._ensure_grader("$2b$12$examplehash")
    user = db.add.call_args.args[0]
    assert (user.username, user.role, user.password_hash) == ("grader", "ADMIN", "$2b$12$examplehash")
    db.commit.assert_awaited_once()


async def test_existing_grader_account_follows_a_changed_hash():
    grader = MagicMock(password_hash="$2b$12$old", role="USER")
    factory, db = fake_session(existing=grader)
    with patch.object(bootstrap, "AsyncSessionLocal", factory):
        await bootstrap._ensure_grader("$2b$12$new")
    assert (grader.password_hash, grader.role) == ("$2b$12$new", "ADMIN")
    db.add.assert_not_called()
    db.commit.assert_awaited_once()
