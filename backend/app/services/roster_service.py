from __future__ import annotations

import csv
import io

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.course import CourseRoster
from ..schemas.admin import RosterUploadResult

logger = structlog.get_logger()

# Canvas gradebook column names (matched case-insensitively)
STUDENT_COL = "student"  # "Last, First [Middle]"
SIS_LOGIN_COL = "sis login id"  # "NETID@WISC.EDU"

MAX_ROWS = 1000


def _is_metadata_row(row: dict[str, str]) -> bool:
    """Skip the Canvas 'Points Possible' row that always appears as row 2."""
    first_val = next(iter(row.values()), "").strip().lower()
    return first_val.startswith("points possible")


def _parse_display_name(raw: str) -> str:
    """
    Extract given name(s) from Canvas 'Last, First [Middle]' format, title-cased.
    Examples:
      "Abboud, Masa"           → "Masa"
      "ABDUL KADIR, KHAYYUM"   → "Khayyum"
      "Bachu, Revanth Krishna" → "Revanth Krishna"
    """
    raw = raw.strip()
    if "," in raw:
        _, _, given = raw.partition(",")
        display = given.strip()
    else:
        display = raw
    return display.title() if display else raw.title()


def _parse_sis_login(raw: str) -> tuple[str, str]:
    """Parse 'NETID@WISC.EDU' into (netid, email), both lowercased."""
    raw = raw.strip().lower()
    netid = raw.partition("@")[0].strip() if "@" in raw else raw
    return netid, raw


async def process_roster_csv(
    db: AsyncSession, course_id: int, file_bytes: bytes
) -> RosterUploadResult:
    """
    Parse a Canvas gradebook CSV export, upsert rows into course_rosters,
    and deactivate entries whose netid is absent from this upload.

    Expected columns (case-insensitive):
      'Student'      — "Last, First [Middle]"
      'SIS Login ID' — "NETID@WISC.EDU"

    Row 2 ('Points Possible') is automatically skipped.
    All other columns are ignored.
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return RosterUploadResult(
            imported=0,
            updated=0,
            deactivated=0,
            errors=["CSV file is empty or has no header row"],
        )

    col_map: dict[str, str] = {f.strip().lower(): f for f in reader.fieldnames}

    missing = {STUDENT_COL, SIS_LOGIN_COL} - col_map.keys()
    if missing:
        return RosterUploadResult(
            imported=0,
            updated=0,
            deactivated=0,
            errors=[
                f"Missing required columns: {', '.join(sorted(missing))}. "
                "Expected 'Student' and 'SIS Login ID' (Canvas gradebook export)."
            ],
        )

    student_header = col_map[STUDENT_COL]
    sis_header = col_map[SIS_LOGIN_COL]

    imported = updated = 0
    errors: list[str] = []
    seen_netids: set[str] = set()
    csv_row = 1  # row 1 = header; incremented before each data row

    for raw_row in reader:
        csv_row += 1

        if _is_metadata_row(raw_row):
            continue

        student_raw = raw_row.get(student_header, "").strip()
        sis_raw = raw_row.get(sis_header, "").strip()

        if not student_raw and not sis_raw:
            continue  # blank trailing row

        row_errors = []
        if not student_raw:
            row_errors.append("Student column is empty")
        if not sis_raw:
            row_errors.append("SIS Login ID column is empty")
        if row_errors:
            errors.append(
                f"Row {csv_row} ('{student_raw or '?'}'): {'; '.join(row_errors)}"
            )
            continue

        display_name = _parse_display_name(student_raw)
        netid, email = _parse_sis_login(sis_raw)

        if not netid:
            errors.append(f"Row {csv_row}: could not extract netid from '{sis_raw}'")
            continue

        if len(seen_netids) >= MAX_ROWS:
            errors.append(
                f"Reached {MAX_ROWS}-row limit; remaining rows were not processed."
            )
            break

        seen_netids.add(netid)

        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == course_id,
                CourseRoster.netid == netid,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.full_name = display_name
            existing.email = email
            existing.is_active = True
            updated += 1
        else:
            db.add(
                CourseRoster(
                    course_id=course_id,
                    netid=netid,
                    full_name=display_name,
                    email=email,
                    is_active=True,
                )
            )
            imported += 1

    await db.flush()

    deactivated = 0
    if seen_netids:
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == course_id,
                CourseRoster.netid.not_in(seen_netids),
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        for entry in result.scalars().all():
            entry.is_active = False
            deactivated += 1

    logger.info(
        "roster_uploaded",
        course_id=course_id,
        imported=imported,
        updated=updated,
        deactivated=deactivated,
        error_count=len(errors),
    )

    return RosterUploadResult(
        imported=imported, updated=updated, deactivated=deactivated, errors=errors
    )


async def process_roster_rows(
    db: AsyncSession, course_id: int, rows: list[dict[str, str]]
) -> RosterUploadResult:
    """
    Process pre-mapped roster rows (already resolved to netid/full_name/email
    by the frontend column-mapping wizard). Upserts into course_rosters and
    deactivates entries whose netid was absent from this upload.
    """
    imported = updated = 0
    errors: list[str] = []
    seen_netids: set[str] = set()

    for i, row in enumerate(rows, start=1):
        netid = row.get("netid", "").strip().lower()
        full_name = row.get("full_name", "").strip()
        email = row.get("email", "").strip().lower()

        if not netid or not full_name or not email:
            errors.append(f"Row {i}: missing required field(s) — skipped")
            continue

        if len(seen_netids) >= MAX_ROWS:
            errors.append(
                f"Reached {MAX_ROWS}-row limit; remaining rows were not processed."
            )
            break

        seen_netids.add(netid)

        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == course_id,
                CourseRoster.netid == netid,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.full_name = full_name
            existing.email = email
            existing.is_active = True
            updated += 1
        else:
            db.add(
                CourseRoster(
                    course_id=course_id,
                    netid=netid,
                    full_name=full_name,
                    email=email,
                    is_active=True,
                )
            )
            imported += 1

    await db.flush()

    deactivated = 0
    if seen_netids:
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == course_id,
                CourseRoster.netid.not_in(seen_netids),
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        for entry in result.scalars().all():
            entry.is_active = False
            deactivated += 1

    logger.info(
        "roster_imported_rows",
        course_id=course_id,
        imported=imported,
        updated=updated,
        deactivated=deactivated,
        error_count=len(errors),
    )

    return RosterUploadResult(
        imported=imported, updated=updated, deactivated=deactivated, errors=errors
    )
