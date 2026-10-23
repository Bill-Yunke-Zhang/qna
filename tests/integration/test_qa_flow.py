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
    def test_switching_and_unaccepting_answers(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        # Losing acceptance also schedules the historical Q&A cleanup
        # (docs/design-rag.md §4.6); it must never fail the request, even
        # with ChromaDB unreachable.
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Which answer?", "body": "Two answers incoming.",
                  "category_ids": [category_id]},
            headers=_headers(student_token),
        )
        assert r.status_code == 201, r.text
        qid = r.json()["id"]
        ids = []
        for token, body in ((staff_token, "First answer."), (student_token, "Second.")):
            r = httpx.post(
                f"{base_url}/api/courses/{course_id}/questions/{qid}/posts",
                json={"kind": "ANSWER", "body": body},
                headers=_headers(token),
            )
            assert r.status_code == 201, r.text
            ids.append(r.json()["posts"][-1]["id"])

        def accept(post_id, value):
            r = httpx.patch(
                f"{base_url}/api/courses/{course_id}/questions/{qid}/posts/{post_id}/accept",
                json={"is_accepted": value},
                headers=_headers(staff_token),
            )
            assert r.status_code == 200, r.text
            return {p["id"]: p["is_accepted"] for p in r.json()["posts"]}

        assert accept(ids[0], True) == {ids[0]: True, ids[1]: False}
        assert accept(ids[1], True) == {ids[0]: False, ids[1]: True}
        assert accept(ids[1], False) == {ids[0]: False, ids[1]: False}

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


class TestAIPostFields:
    """
    AI posts themselves are written by a background task, not an endpoint,
    so these check the HTTP surface around them (docs/design-rag.md §4).
    """

    def test_human_posts_carry_the_new_fields_and_cannot_be_retracted(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Retract me?", "body": "Body.", "category_ids": [category_id]},
            headers=_headers(student_token),
        )
        assert r.status_code == 201, r.text
        qid = r.json()["id"]
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{qid}/posts",
            json={"kind": "ANSWER", "body": "Human answer."},
            headers=_headers(staff_token),
        )
        post = r.json()["posts"][0]
        assert post["citations"] is None
        assert post["retracted_at"] is None and post["retracted_by"] is None

        url = f"{base_url}/api/courses/{course_id}/questions/{qid}/posts/{post['id']}/retract"
        # Staff only, and only AI posts.
        r = httpx.patch(url, headers=_headers(student_token))
        assert r.status_code == 403, r.text
        r = httpx.patch(url, headers=_headers(staff_token))
        assert r.status_code == 422, r.text

        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions", headers=_headers(student_token)
        )
        listed = next(x for x in r.json() if x["id"] == qid)
        assert listed["has_ai_answer"] is False and listed["post_count"] == 1


class TestWritesCommitBeforeResponding:
    def test_granted_access_works_on_the_very_next_request(
        self, base_url, course_id, admin_token
    ):
        # Write routes must commit before responding: get_db's own commit
        # runs after the response is sent, and without an explicit one a
        # client that used its new access right away got a 404 (39 of 40
        # times locally). It only shows on a reused (keep-alive) connection,
        # as a browser uses; a new connection per request is slow enough to
        # hide it, so this test grants and uses access on one client.
        import uuid

        api = f"{base_url}/api"
        admin = _headers(admin_token)
        with httpx.Client(timeout=10.0) as c:
            for _ in range(10):
                netid = f"test-race-{uuid.uuid4().hex[:8]}"
                temp = c.post(f"{api}/auth/login", json={"netid": netid}).json()["temp_token"]
                token = c.post(
                    f"{api}/auth/exchange-temp", headers=_headers(temp)
                ).json()["access_token"]
                user_id = next(
                    u["id"] for u in c.get(f"{api}/admin/users", headers=admin).json()
                    if u["netid"] == netid
                )
                r = c.post(
                    f"{api}/admin/users/{user_id}/course-access",
                    json={"course_id": course_id, "role": "STAFF"},
                    headers=admin,
                )
                assert r.status_code == 204, r.text
                r = c.get(f"{api}/courses/{course_id}/questions", headers=_headers(token))
                assert r.status_code == 200, r.text


class TestLiveAnswering:
    def test_question_posts_normally_and_gets_no_ai_answer_without_content(
        self, base_url, course_id, student_token, category_id
    ):
        # create_question schedules answer_question after committing
        # (docs/design-rag.md §5.4). A fresh course has nothing ingested, so
        # the task must post nothing, and must never affect the question.
        import time

        started = time.monotonic()
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Any AI?", "body": "Nothing is ingested here.",
                  "category_ids": [category_id]},
            headers=_headers(student_token),
        )
        assert r.status_code == 201, r.text
        # The answer runs after the response, so posting stays fast.
        assert time.monotonic() - started < 5
        qid = r.json()["id"]
        time.sleep(2)
        r = httpx.get(
            f"{base_url}/api/courses/{course_id}/questions/{qid}",
            headers=_headers(student_token),
        )
        assert r.status_code == 200, r.text
        assert [p for p in r.json()["posts"] if p["author_role"] == "AI"] == []
