"""
Integration tests for the core Q&A thread flow, run against the live Docker
stack. These cover the baseline (no-AI) behavior this starter ships with —
extend this file, don't weaken it, as you add the RAG feature.
"""
from __future__ import annotations

import httpx


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestThreadLifecycle:
    def test_student_asks_staff_answers_and_accepts(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        # Student posts a question
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={
                "title": "Why does my container hang?",
                "body": "Details here.",
                "category_ids": [category_id],
            },
            headers=_headers(student_token),
        )
        assert r.status_code == 201, r.text
        question = r.json()
        assert question["status"] == "OPEN"
        assert question["author"]["display_name"]

        # Staff answers
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question['id']}/posts",
            json={"kind": "ANSWER", "body": "Run migrations."},
            headers=_headers(staff_token),
        )
        assert r.status_code == 201, r.text
        detail = r.json()
        assert len(detail["posts"]) == 1
        post = detail["posts"][0]
        assert post["author_role"] == "STAFF"
        assert post["is_accepted"] is False

        # Staff marks the answer accepted
        r = httpx.patch(
            f"{base_url}/api/courses/{course_id}/questions/{question['id']}/posts/{post['id']}/accept",
            json={"is_accepted": True},
            headers=_headers(staff_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["posts"][0]["is_accepted"] is True

        # Reflected in the list view
        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions", headers=_headers(student_token)
        )
        assert r.status_code == 200
        listed = next(q for q in r.json() if q["id"] == question["id"])
        assert listed["has_accepted_answer"] is True

    def test_student_can_answer_and_staff_can_verify_it(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={
                "title": "Anyone solved the FK constraint?",
                "body": "…",
                "category_ids": [category_id],
            },
            headers=_headers(student_token),
        )
        question_id = r.json()["id"]

        # The asker's own peer answers (any enrolled student may answer)
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "ANSWER", "body": "Drop and recreate the FK."},
            headers=_headers(student_token),
        )
        assert r.status_code == 201, r.text
        post = r.json()["posts"][0]
        assert post["author_role"] == "STUDENT"

        # Staff can mark a student's answer verified, same mechanism as any answer
        r = httpx.patch(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts/{post['id']}/accept",
            json={"is_accepted": True},
            headers=_headers(staff_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["posts"][0]["accepted_by"] is not None

    def test_followup_cannot_be_accepted(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q", "body": "B", "category_ids": [category_id]},
            headers=_headers(student_token),
        )
        question_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "FOLLOWUP", "body": "Can you clarify?"},
            headers=_headers(student_token),
        )
        post_id = r.json()["posts"][0]["id"]

        r = httpx.patch(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts/{post_id}/accept",
            json={"is_accepted": True},
            headers=_headers(staff_token),
        )
        assert r.status_code == 409

    def test_closing_a_thread_blocks_new_posts_until_reopened(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q", "body": "B", "category_ids": [category_id]},
            headers=_headers(student_token),
        )
        question_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/close",
            headers=_headers(staff_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "CLOSED"

        # Neither students nor staff can post to a closed thread
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "FOLLOWUP", "body": "one more thing"},
            headers=_headers(student_token),
        )
        assert r.status_code == 409

        # A student cannot close or reopen a thread — staff-only
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/reopen",
            headers=_headers(student_token),
        )
        assert r.status_code == 403

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/reopen",
            headers=_headers(staff_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "OPEN"

        # Posting works again once reopened
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "FOLLOWUP", "body": "thanks!"},
            headers=_headers(student_token),
        )
        assert r.status_code == 201


class TestCategoriesAndFiltering:
    def test_only_staff_can_manage_categories(self, base_url, course_id, student_token, staff_token):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Docker", "description": ""},
            headers=_headers(student_token),
        )
        assert r.status_code == 403

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Docker", "description": ""},
            headers=_headers(staff_token),
        )
        assert r.status_code == 201

    def test_category_filter_and_keyword_search(self, base_url, course_id, student_token, staff_token):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Git", "description": ""},
            headers=_headers(staff_token),
        )
        git_category_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Docker", "description": ""},
            headers=_headers(staff_token),
        )
        docker_category_id = r.json()["id"]

        httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Merge conflict help", "body": "…", "category_ids": [git_category_id]},
            headers=_headers(student_token),
        )
        httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={
                "title": "Docker healthcheck failing",
                "body": "…",
                "category_ids": [docker_category_id],
            },
            headers=_headers(student_token),
        )

        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions",
            params={"category_id": git_category_id},
            headers=_headers(student_token),
        )
        titles = [q["title"] for q in r.json()]
        assert titles == ["Merge conflict help"]

        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions",
            params={"q": "healthcheck"},
            headers=_headers(student_token),
        )
        titles = [q["title"] for q in r.json()]
        assert titles == ["Docker healthcheck failing"]


class TestAccessControl:
    def test_non_member_cannot_see_course(self, base_url, course_id):
        # A brand new netid with no course-access grant should not be able to
        # discover this course exists.
        import uuid

        netid = f"outsider-{uuid.uuid4().hex[:8]}"
        r = httpx.post(f"{base_url}/api/auth/login", json={"netid": netid})
        temp_token = r.json()["temp_token"]
        r = httpx.post(
            f"{base_url}/api/auth/exchange-temp",
            headers={"Authorization": f"Bearer {temp_token}"},
        )
        outsider_token = r.json()["access_token"]

        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions",
            headers=_headers(outsider_token),
        )
        assert r.status_code == 404
