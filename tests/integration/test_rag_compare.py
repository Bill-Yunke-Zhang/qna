"""
Integration tests for POST /api/courses/{course_id}/rag/compare (T6,
docs/design-rag.md §5.3), against the live stack.

The harness aborts a whole run on any error status, so these pin down the
checks that happen before the pipeline runs: who may call it, which course,
and what a valid body is. Retrieval and generation are covered once the
pipeline exists; they need Ollama, Infinity and ingested content.
"""
from __future__ import annotations

import httpx
import pytest

BASELINE = {
    "question": "When is P1 due?",
    "ingestion_profile": "sliding-window",
    "similarity_threshold": 0.5,
    "system_prompt": (
        "Only use the information provided in the tagged context to answer "
        "questions. If the context does not contain enough information to "
        "answer, say so rather than guessing."
    ),
    "generation_model": "qwen2.5:1.5b",
}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _url(base_url: str, course_id: int) -> str:
    return f"{base_url}/api/courses/{course_id}/rag/compare"


class TestCompareAccess:
    def test_students_cannot_compare(self, base_url, course_id, student_token):
        r = httpx.post(_url(base_url, course_id), json=BASELINE, headers=_headers(student_token))
        assert r.status_code == 403, r.text

    def test_staff_app_surface_header_cannot_unlock_it_for_a_student(
        self, base_url, course_id, student_token
    ):
        # X-App-Surface only ever restricts.
        r = httpx.post(
            _url(base_url, course_id),
            json=BASELINE,
            headers={**_headers(student_token), "X-App-Surface": "staff"},
        )
        assert r.status_code == 403, r.text

    def test_unauthenticated_is_rejected(self, base_url, course_id):
        r = httpx.post(_url(base_url, course_id), json=BASELINE)
        assert r.status_code in (401, 403), r.text

    def test_unknown_course_is_404_for_admin(self, base_url, admin_token):
        # An admin passes the staff check for any course id, so the endpoint
        # must check the course exists before running the pipeline.
        r = httpx.post(_url(base_url, 999_999_999), json=BASELINE, headers=_headers(admin_token))
        assert r.status_code == 404, r.text
        assert r.json()["error"] == "NOT_FOUND"


class TestCompareBody:
    @pytest.mark.parametrize(
        "change",
        [
            {"question": ""},
            {"similarity_threshold": 1.5},
            {"similarity_threshold": "high"},
            {"generation_model": ""},
            {"ingestion_profile": ""},
            {"unexpected": "field"},
        ],
        ids=["empty-question", "threshold>1", "threshold-not-number", "no-model", "no-profile", "extra-field"],
    )
    def test_invalid_body_is_422(self, base_url, course_id, staff_token, change):
        r = httpx.post(
            _url(base_url, course_id), json={**BASELINE, **change}, headers=_headers(staff_token)
        )
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("missing", list(BASELINE))
    def test_every_contract_field_is_required(self, base_url, course_id, staff_token, missing):
        body = {k: v for k, v in BASELINE.items() if k != missing}
        r = httpx.post(_url(base_url, course_id), json=body, headers=_headers(staff_token))
        assert r.status_code == 422, r.text
