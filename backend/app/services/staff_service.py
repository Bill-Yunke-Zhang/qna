from __future__ import annotations

import csv
import io
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.course import UserCourseAccess
from ..models.user import User
from ..schemas.admin import StaffUploadResult

logger = structlog.get_logger()

NETID_COL = "netid"
FULL_NAME_COL = "full_name"
EMAIL_COL = "email"

MAX_ROWS = 200


async def process_staff_csv(
    db: AsyncSession, course_id: int, file_bytes: bytes
) -> StaffUploadResult:
    """
    Parse a staff CSV (columns: netid, full_name, email — case-insensitive)
    and, for each row:
      - create the User account if it doesn't exist yet (or reuse it if it
        does — e.g. someone who already logged in once, or is staff in
        another course)
      - grant STAFF course access for this course, upgrading an existing
        STUDENT grant if one exists

    Unlike the student roster upload, this takes effect immediately — a
    newly listed staff member doesn't need to log in first before an admin
    can grant them access, since course staff lists are small and staff
    need access from day one.
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return StaffUploadResult(
            accounts_created=0,
            access_granted=0,
            already_staff=0,
            errors=["CSV file is empty or has no header row"],
        )

    col_map: dict[str, str] = {f.strip().lower(): f for f in reader.fieldnames}
    missing = {NETID_COL, FULL_NAME_COL, EMAIL_COL} - col_map.keys()
    if missing:
        return StaffUploadResult(
            accounts_created=0,
            access_granted=0,
            already_staff=0,
            errors=[
                f"Missing required columns: {', '.join(sorted(missing))}. "
                "Expected 'netid', 'full_name', and 'email'."
            ],
        )

    netid_header = col_map[NETID_COL]
    name_header = col_map[FULL_NAME_COL]
    email_header = col_map[EMAIL_COL]

    accounts_created = access_granted = already_staff = 0
    errors: list[str] = []
    seen_netids: set[str] = set()
    csv_row = 1  # row 1 = header; incremented before each data row

    for raw_row in reader:
        csv_row += 1

        netid = raw_row.get(netid_header, "").strip().lower()
        full_name = raw_row.get(name_header, "").strip()
        email = raw_row.get(email_header, "").strip().lower()

        if not netid and not full_name and not email:
            continue  # blank trailing row

        row_errors = []
        if not netid:
            row_errors.append("netid is empty")
        if not full_name:
            row_errors.append("full_name is empty")
        if not email:
            row_errors.append("email is empty")
        if row_errors:
            errors.append(
                f"Row {csv_row} ('{full_name or netid or '?'}'): {'; '.join(row_errors)}"
            )
            continue

        if netid in seen_netids:
            errors.append(
                f"Row {csv_row}: duplicate netid '{netid}' in this file — skipped"
            )
            continue
        if len(seen_netids) >= MAX_ROWS:
            errors.append(
                f"Reached {MAX_ROWS}-row limit; remaining rows were not processed."
            )
            break
        seen_netids.add(netid)

        result = await db.execute(select(User).where(User.netid == netid))
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=str(uuid.uuid4()), netid=netid, email=email, role="USER")
            db.add(user)
            await db.flush()
            accounts_created += 1
        elif not user.email:
            user.email = email
        if not user.display_name:
            user.display_name = full_name

        result = await db.execute(
            select(UserCourseAccess).where(
                UserCourseAccess.user_id == user.id,
                UserCourseAccess.course_id == course_id,
            )
        )
        access = result.scalar_one_or_none()
        if access:
            if access.role != "STAFF":
                access.role = "STAFF"
                access_granted += 1
            else:
                already_staff += 1
        else:
            db.add(UserCourseAccess(user_id=user.id, course_id=course_id, role="STAFF"))
            access_granted += 1

    await db.flush()

    logger.info(
        "staff_csv_processed",
        course_id=course_id,
        accounts_created=accounts_created,
        access_granted=access_granted,
        already_staff=already_staff,
        error_count=len(errors),
    )

    return StaffUploadResult(
        accounts_created=accounts_created,
        access_granted=access_granted,
        already_staff=already_staff,
        errors=errors,
    )
