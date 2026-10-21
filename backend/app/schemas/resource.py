from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ResourceType = Literal["SYLLABUS", "SCHEDULE", "REPO"]

# ---------------------------------------------------------------------------
# Requests (docs/design-rag.md §7.2, §7.5). Uploads are multipart forms, so
# their fields are declared on the route instead.
# ---------------------------------------------------------------------------


class ResourceCreate(BaseModel):
    """Register a URL resource."""

    model_config = ConfigDict(extra="forbid")
    type: ResourceType
    title: str = Field(..., min_length=1, max_length=255)
    fetch_url: str = Field(..., min_length=1, max_length=2048)
    repo_branch: str | None = Field(None, min_length=1, max_length=255)
    profiles: list[str] | None = None

    @model_validator(mode="after")
    def branch_only_for_repos(self) -> ResourceCreate:
        if self.type == "REPO" and not self.repo_branch:
            raise ValueError("repo_branch is required for a REPO resource")
        if self.type != "REPO" and self.repo_branch is not None:
            raise ValueError("repo_branch is only for REPO resources")
        return self


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profiles: list[str] | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SyncStatus(BaseModel):
    """One `index_syncs` row: a source's last sync under one profile."""

    model_config = ConfigDict(from_attributes=True)
    profile: str
    last_synced_at: datetime | None
    chunk_count: int
    truncated_chunk_count: int
    commit_sha: str | None
    last_error: str | None
    last_error_at: datetime | None


class ResourceResponse(BaseModel):
    id: int
    type: ResourceType
    title: str
    origin: Literal["URL", "UPLOAD"]
    fetch_url: str | None
    link_base_url: str | None
    repo_branch: str | None
    created_at: datetime
    syncing: bool
    # The source's profiles hold different versions of it (§7.3).
    version_mismatch: bool
    syncs: list[SyncStatus]


class HistoricalQAResponse(BaseModel):
    syncing: bool
    version_mismatch: bool
    syncs: list[SyncStatus]


class ResourceListResponse(BaseModel):
    live_profile: str
    profiles: list[str]
    resources: list[ResourceResponse]
    historical_qa: HistoricalQAResponse
