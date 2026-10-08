"""
On first startup, create the initial admin user if ADMIN_USERNAME and
ADMIN_PASSWORD are set and no ADMIN account exists yet.

This runs once inside the lifespan startup hook. After the first admin
exists the env vars are ignored — remove them from .env if you like,
or leave them (they simply become a no-op).

It also keeps the course grader account in step with GRADER_PASSWORD_HASH
(base64 of a bcrypt hash that course staff publish in .env.template): an
ADMIN user named "grader" whose password only staff know. Unlike the first
admin this is applied on every startup, so a corrected hash takes effect on
the next restart.

On a fresh database the schema doesn't exist until `alembic upgrade head`
has been run, so this retries instead of crashing: startup blocks (with a
log line every few seconds) until migrations land, then completes on its
own.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.user import User
from .auth_service import hash_password

logger = structlog.get_logger()

RETRY_SECONDS = 5
GRADER_USERNAME = "grader"


def grader_password_hash() -> str | None:
    """The bcrypt hash carried by GRADER_PASSWORD_HASH, or None if it is unset or
    is not base64 of a bcrypt hash (logged, never fatal)."""
    raw = settings.GRADER_PASSWORD_HASH.strip()
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        decoded = ""
    if not decoded.startswith("$2"):
        logger.warning(
            "grader_hash_invalid",
            hint="copy GRADER_PASSWORD_HASH from .env.template unchanged",
        )
        return None
    return decoded


async def bootstrap_admin() -> None:
    create_admin = bool(settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD)
    grader_hash = grader_password_hash()
    if not create_admin and grader_hash is None:
        return

    while True:
        try:
            if create_admin:
                await _create_admin_if_missing()
            if grader_hash is not None:
                await _ensure_grader(grader_hash)
            return
        except ProgrammingError:
            # Fresh database: the schema doesn't exist yet.
            logger.warning(
                "admin_bootstrap_waiting_for_schema",
                hint="run `docker compose run --rm backend alembic upgrade head` "
                "to create the schema; startup will finish on its own",
            )
        except OperationalError as exc:
            logger.warning("admin_bootstrap_retrying", error=str(exc.orig))
        await asyncio.sleep(RETRY_SECONDS)


async def _create_admin_if_missing() -> None:
    async with AsyncSessionLocal() as db:
        # The grader account doesn't count: it must never stand in for your own admin.
        result = await db.execute(
            select(User)
            .where(User.role == "ADMIN", User.username != GRADER_USERNAME)
            .limit(1)
        )
        if result.scalars().first() is not None:
            return  # admin already exists

        admin = User(
            id=str(uuid.uuid4()),
            username=settings.ADMIN_USERNAME.lower(),
            display_name="Admin",
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role="ADMIN",
        )
        db.add(admin)
        await db.commit()
        logger.info("admin_bootstrapped", username=settings.ADMIN_USERNAME.lower())


async def _ensure_grader(password_hash: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == GRADER_USERNAME).limit(1)
        )
        grader = result.scalars().first()
        if grader is None:
            db.add(
                User(
                    id=str(uuid.uuid4()),
                    username=GRADER_USERNAME,
                    display_name="Course Grader",
                    password_hash=password_hash,
                    role="ADMIN",
                )
            )
        elif grader.password_hash == password_hash and grader.role == "ADMIN":
            return
        else:
            grader.password_hash = password_hash
            grader.role = "ADMIN"
        await db.commit()
        logger.info("grader_account_ready", username=GRADER_USERNAME)
