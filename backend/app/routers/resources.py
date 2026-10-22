"""
Staff resource management: register, upload, re-sync and delete course
material for RAG ingestion, and re-index historical Q&A
(docs/design-rag.md §3.2, §7.2, §7.5). Every route is staff-only and scoped
by the `course_id` in the path; a sync is accepted with 202 and runs in the
background, and its result shows up in `GET /resources`.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import CourseMember, require_course_staff
from ..common.exceptions import ConflictError, InvalidInputError
from ..common.uploads import read_upload_capped
from ..config import settings
from ..database import get_db
from ..models.resource import HISTORICAL_QA_SOURCE_KEY, Resource
from ..schemas.resource import (
    HistoricalQAResponse,
    ResourceCreate,
    ResourceListResponse,
    ResourceResponse,
    ResourceType,
    SyncRequest,
)
from ..services import resource_service
from ..services.rag import fetchers, ingestion

router = APIRouter(prefix="/courses/{course_id}", tags=["resources"])

Staff = Annotated[CourseMember, Depends(require_course_staff)]
Db = Annotated[AsyncSession, Depends(get_db)]


async def _parse_upload(
    file: UploadFile, resource_type: str, link_base_url: str
) -> list[ingestion.Document]:
    """Checked and parsed in the request, so a bad file is a 422 (§7.2)."""
    data = await read_upload_capped(file, max_bytes=settings.UPLOAD_MAX_BYTES)
    try:
        return await asyncio.to_thread(
            ingestion.parse_upload,
            resource_type,
            link_base_url,
            file.filename or "",
            data,
        )
    except fetchers.FetchError as exc:  # UploadError, or a page with no text
        raise InvalidInputError(str(exc)) from None


async def _accepted(db: AsyncSession, resource: Resource) -> dict:
    rows = await resource_service.source_rows(
        db, resource.course_id, resource.source_key
    )
    return resource_service.resource_response(resource, rows)


@router.get("/resources", response_model=ResourceListResponse)
async def list_resources(course_id: int, _: Staff, db: Db) -> dict:
    return await resource_service.list_resources(db, course_id)


@router.post("/resources", response_model=ResourceResponse, status_code=202)
async def register_resource(
    course_id: int,
    body: ResourceCreate,
    member: Staff,
    db: Db,
    background_tasks: BackgroundTasks,
) -> dict:
    await resource_service.require_course(db, course_id)
    profiles = resource_service.resolve_profiles(
        body.profiles, [settings.RAG_LIVE_PROFILE]
    )
    fetch_url = await resource_service.check_fetch_url(
        body.type, body.fetch_url, body.repo_branch
    )
    resource = await resource_service.create_resource(
        db,
        course_id,
        member.user,
        resource_type=body.type,
        title=body.title,
        origin="URL",
        fetch_url=fetch_url,
        repo_branch=body.repo_branch,
    )
    await db.commit()
    await resource_service.start_sync(
        background_tasks,
        course_id=course_id,
        source_key=resource.source_key,
        resource_id=resource.id,
        title=resource.title,
        profiles=profiles,
        load=resource_service.sync_loader(resource),
    )
    return await _accepted(db, resource)


@router.post("/resources/upload", response_model=ResourceResponse, status_code=202)
async def upload_resource(
    course_id: int,
    type: Annotated[ResourceType, Form()],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    link_base_url: Annotated[str, Form(min_length=1, max_length=2048)],
    file: Annotated[UploadFile, File()],
    member: Staff,
    db: Db,
    background_tasks: BackgroundTasks,
    profiles: Annotated[str | None, Form()] = None,
) -> dict:
    await resource_service.require_course(db, course_id)
    names = resource_service.resolve_profiles(
        resource_service.parse_profiles_field(profiles), [settings.RAG_LIVE_PROFILE]
    )
    resource_service.check_link_base_url(link_base_url)
    documents = await _parse_upload(file, type, link_base_url)
    resource = await resource_service.create_resource(
        db,
        course_id,
        member.user,
        resource_type=type,
        title=title,
        origin="UPLOAD",
        link_base_url=link_base_url,
    )
    await db.commit()
    await resource_service.start_sync(
        background_tasks,
        course_id=course_id,
        source_key=resource.source_key,
        resource_id=resource.id,
        title=resource.title,
        profiles=names,
        load=ingestion.documents_loader(documents),
    )
    return await _accepted(db, resource)


@router.post(
    "/resources/{resource_id}/sync", response_model=ResourceResponse, status_code=202
)
async def resync_resource(
    course_id: int,
    resource_id: int,
    _: Staff,
    db: Db,
    background_tasks: BackgroundTasks,
    body: SyncRequest | None = None,
) -> dict:
    resource = await resource_service.get_resource(db, course_id, resource_id)
    if resource.origin != "URL":
        raise ConflictError("This resource was uploaded; upload a new file instead")
    default = await resource_service.default_profiles(
        db, course_id, resource.source_key
    )
    profiles = resource_service.resolve_profiles(body and body.profiles, default)
    await resource_service.start_sync(
        background_tasks,
        course_id=course_id,
        source_key=resource.source_key,
        resource_id=resource.id,
        title=resource.title,
        profiles=profiles,
        load=resource_service.sync_loader(resource),
    )
    return await _accepted(db, resource)


@router.put(
    "/resources/{resource_id}/upload", response_model=ResourceResponse, status_code=202
)
async def replace_upload(
    course_id: int,
    resource_id: int,
    file: Annotated[UploadFile, File()],
    _: Staff,
    db: Db,
    background_tasks: BackgroundTasks,
    profiles: Annotated[str | None, Form()] = None,
) -> dict:
    """
    A new file for an uploaded resource. It keeps the resource's id and
    `index_syncs` rows, so searches switch to the new content with no gap
    (§3.2).
    """
    resource = await resource_service.get_resource(db, course_id, resource_id)
    if resource.origin != "UPLOAD":
        raise ConflictError("This resource is fetched from a URL; re-sync it instead")
    default = await resource_service.default_profiles(
        db, course_id, resource.source_key
    )
    names = resource_service.resolve_profiles(
        resource_service.parse_profiles_field(profiles), default
    )
    if ingestion.is_syncing(course_id, resource.source_key):
        # Checked before parsing a possibly large file; start_sync rechecks.
        raise ConflictError("This source is already syncing")
    documents = await _parse_upload(file, resource.type, resource.link_base_url)
    await resource_service.start_sync(
        background_tasks,
        course_id=course_id,
        source_key=resource.source_key,
        resource_id=resource.id,
        title=resource.title,
        profiles=names,
        load=ingestion.documents_loader(documents),
    )
    return await _accepted(db, resource)


@router.delete("/resources/{resource_id}", status_code=204)
async def delete_resource(course_id: int, resource_id: int, _: Staff, db: Db) -> None:
    resource = await resource_service.get_resource(db, course_id, resource_id)
    await resource_service.delete_resource(db, course_id, resource)
    await db.commit()


@router.post(
    "/historical-qa/sync", response_model=HistoricalQAResponse, status_code=202
)
async def reindex_historical_qa(
    course_id: int,
    _: Staff,
    db: Db,
    background_tasks: BackgroundTasks,
    body: SyncRequest | None = None,
) -> dict:
    await resource_service.require_course(db, course_id)
    default = await resource_service.default_profiles(
        db, course_id, HISTORICAL_QA_SOURCE_KEY
    )
    profiles = resource_service.resolve_profiles(body and body.profiles, default)
    await resource_service.start_sync(
        background_tasks,
        course_id=course_id,
        source_key=HISTORICAL_QA_SOURCE_KEY,
        resource_id=None,
        title=ingestion.HISTORICAL_QA_TITLE,
        profiles=profiles,
        load=ingestion.historical_qa_loader(course_id),
    )
    rows = await resource_service.source_rows(db, course_id, HISTORICAL_QA_SOURCE_KEY)
    return resource_service.source_status(course_id, HISTORICAL_QA_SOURCE_KEY, rows)
