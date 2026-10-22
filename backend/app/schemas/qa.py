from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=1000)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    name: str
    description: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=10000)
    category_ids: list[int] = Field(..., min_length=1)


class AuthorSummary(BaseModel):
    id: str
    display_name: str


class QuestionSummary(BaseModel):
    id: int
    course_id: int
    title: str
    status: str
    author: AuthorSummary
    categories: list[CategoryResponse]
    # Retracted AI posts aren't counted, for any viewer (docs/design-rag.md §4.7).
    post_count: int
    has_accepted_answer: bool
    # A non-retracted AI answer exists; staff use it to find AI answers to check.
    has_ai_answer: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Posts (answers + follow-ups within a question's thread)
# ---------------------------------------------------------------------------


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(..., pattern="^(ANSWER|FOLLOWUP)$")
    body: str = Field(..., min_length=1, max_length=10000)


class Citation(BaseModel):
    """
    One source an AI answer was given (docs/design-rag.md §3.1, §3.3), saved
    on the post when it's created. Historical Q&A has no `citation_url`;
    each frontend links to its own thread page from `question_id`.
    """

    model_config = ConfigDict(extra="forbid")
    rank: int = Field(..., ge=1, le=3)
    label: str = Field(..., min_length=1, max_length=500)
    resource_type: Literal[
        "syllabus", "schedule", "repo_markdown", "repo_pdf", "historical_qa"
    ]
    citation_url: str | None = Field(None, max_length=2048)
    question_id: int | None = None
    similarity_score: float

    @model_validator(mode="after")
    def _location_fits_type(self) -> Citation:
        if self.resource_type == "historical_qa":
            if self.question_id is None or self.citation_url is not None:
                raise ValueError("a historical_qa citation has question_id only")
        elif self.citation_url is None or self.question_id is not None:
            raise ValueError(f"a {self.resource_type} citation has citation_url only")
        return self


class AICitations(BaseModel):
    """What an AI post must carry: 1–3 citations with unique ranks, best first."""

    model_config = ConfigDict(extra="forbid")
    citations: list[Citation] = Field(..., min_length=1, max_length=3)

    @model_validator(mode="after")
    def _ranks_are_1_to_n(self) -> AICitations:
        ranks = [c.rank for c in self.citations]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("citation ranks must be 1..n in order")
        return self


class PostResponse(BaseModel):
    id: int
    question_id: int
    # None for AI posts (author_role "AI"), which have no author user.
    author: AuthorSummary | None
    author_role: str
    kind: str
    body: str
    is_accepted: bool
    accepted_by: AuthorSummary | None
    accepted_at: datetime | None
    created_at: datetime
    citations: list[Citation] | None
    # Only staff ever receive retracted posts; students don't see them at all.
    # `retracted_by` is None if that staff user was deleted ("by staff").
    retracted_at: datetime | None
    retracted_by: AuthorSummary | None


class PostAcceptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_accepted: bool


class QuestionDetail(BaseModel):
    id: int
    course_id: int
    title: str
    body: str
    status: str
    author: AuthorSummary
    categories: list[CategoryResponse]
    posts: list[PostResponse]
    closed_by: AuthorSummary | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Course membership (for the app's course picker)
# ---------------------------------------------------------------------------


class MyCourseResponse(BaseModel):
    id: int
    name: str
    semester: str
    role: str
