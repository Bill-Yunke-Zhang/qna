from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    post_count: int
    has_accepted_answer: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Posts (answers + follow-ups within a question's thread)
# ---------------------------------------------------------------------------


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(..., pattern="^(ANSWER|FOLLOWUP)$")
    body: str = Field(..., min_length=1, max_length=10000)


class PostResponse(BaseModel):
    id: int
    question_id: int
    author: AuthorSummary
    author_role: str
    kind: str
    body: str
    is_accepted: bool
    accepted_by: AuthorSummary | None
    accepted_at: datetime | None
    created_at: datetime


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
