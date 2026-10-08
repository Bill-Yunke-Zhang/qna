"""
Security-focused integration tests, run against the live Docker stack.

Unlike test_qa_flow.py (which covers ordinary feature behavior), every test
in this file exists because something *should never be possible* — a
privilege escalation, a cross-tenant data leak, or an authentication
bypass. A failure here means a security regression, not a feature bug.
"""
from __future__ import annotations

import httpx


def admin_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestOauth2HeaderSpoofing:
    def test_spoofed_sso_headers_are_rejected(self, base_url, docker_stack):
        """
        X-Auth-Request-User/-Email are meant to be set only by a trusted
        OAuth2 reverse proxy, never by the client directly. Without a
        matching X-Proxy-Shared-Secret (unset in this test stack — see
        OAUTH2_PROXY_SHARED_SECRET in .env), the callback must refuse the
        request no matter how legitimate the headers look.
        """
        r = httpx.get(
            f"{base_url}/api/auth/oauth2-callback",
            headers={
                "X-Auth-Request-User": "wisebeaver",
                "X-Auth-Request-Email": "wisebeaver@example.edu",
            },
        )
        assert r.status_code == 200  # always 200 — it's an HTML redirect page
        assert "temp_token" not in r.text
        assert "error=" in r.text


class TestSurfaceClamping:
    """
    The Student app sends X-App-Surface: student on every request, which
    clamps the caller's effective course role to STUDENT no matter their
    real capability (see require_course_member in common/dependencies.py).
    This is what stops a staff member or admin testing the Student app from
    quietly acting with staff privileges — and it must be a hard clamp, not
    just something the frontend happens to respect.
    """

    def test_staff_posting_via_student_surface_is_attributed_as_student(
        self, base_url, course_id, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q", "body": "B", "category_ids": [category_id]},
            headers={**admin_headers(staff_token), "X-App-Surface": "student"},
        )
        assert r.status_code == 201, r.text
        question_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "FOLLOWUP", "body": "hi"},
            headers={**admin_headers(staff_token), "X-App-Surface": "student"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["posts"][-1]["author_role"] == "STUDENT"

    def test_staff_only_action_blocked_via_student_surface(
        self, base_url, course_id, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q", "body": "B", "category_ids": [category_id]},
            headers=admin_headers(staff_token),
        )
        question_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{question_id}/close",
            headers={**admin_headers(staff_token), "X-App-Surface": "student"},
        )
        assert r.status_code == 403

    def test_admin_via_student_surface_cannot_manage_categories(
        self, base_url, course_id, admin_token
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Sneaky", "description": ""},
            headers={**admin_headers(admin_token), "X-App-Surface": "student"},
        )
        assert r.status_code == 403

    def test_surface_header_cannot_grant_staff_to_a_real_student(
        self, base_url, course_id, student_token
    ):
        """The header can only ever clamp toward STUDENT, never grant STAFF —
        a real student claiming X-App-Surface: staff must still be denied."""
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/categories",
            json={"name": "Should Fail", "description": ""},
            headers={**admin_headers(student_token), "X-App-Surface": "staff"},
        )
        assert r.status_code == 403


class TestAdminAccessControl:
    def test_student_cannot_list_admin_courses(self, base_url, student_token):
        r = httpx.get(f"{base_url}/api/admin/courses", headers=admin_headers(student_token))
        assert r.status_code == 403

    def test_staff_cannot_create_course(self, base_url, staff_token):
        r = httpx.post(
            f"{base_url}/api/admin/courses",
            json={"name": "Should Not Exist", "semester": "Nope"},
            headers=admin_headers(staff_token),
        )
        assert r.status_code == 403

    def test_unauthenticated_cannot_list_admin_users(self, base_url, docker_stack):
        r = httpx.get(f"{base_url}/api/admin/users")
        assert r.status_code == 401

    def test_student_cannot_upload_roster(self, base_url, course_id, student_token):
        files = {"file": ("roster.csv", "Student,SIS Login ID\n", "text/csv")}
        r = httpx.post(
            f"{base_url}/api/admin/courses/{course_id}/roster",
            files=files,
            headers=admin_headers(student_token),
        )
        assert r.status_code == 403

    def test_student_cannot_upload_staff_csv(self, base_url, course_id, student_token):
        files = {"file": ("staff.csv", "netid,full_name,email\n", "text/csv")}
        r = httpx.post(
            f"{base_url}/api/admin/courses/{course_id}/staff",
            files=files,
            headers=admin_headers(student_token),
        )
        assert r.status_code == 403

    def test_student_cannot_grant_course_access(self, base_url, course_id, student_token):
        r = httpx.post(
            f"{base_url}/api/admin/users/nonexistent-id/course-access",
            json={"course_id": course_id, "role": "STAFF"},
            headers=admin_headers(student_token),
        )
        assert r.status_code == 403


class TestCrossResourceIDOR:
    def test_cannot_attach_another_courses_category_to_a_question(
        self, base_url, admin_token, course_id, student_token
    ):
        r = httpx.post(
            f"{base_url}/api/admin/courses",
            json={"name": "Other Course", "semester": "Test"},
            headers=admin_headers(admin_token),
        )
        other_course_id = r.json()["id"]
        r = httpx.post(
            f"{base_url}/api/courses/{other_course_id}/categories",
            json={"name": "Foreign", "description": ""},
            headers=admin_headers(admin_token),  # ADMIN acts as staff everywhere
        )
        foreign_category_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q", "body": "B", "category_ids": [foreign_category_id]},
            headers=admin_headers(student_token),
        )
        assert r.status_code == 404

    def test_cannot_accept_a_post_through_a_different_questions_url(
        self, base_url, course_id, student_token, staff_token, category_id
    ):
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q1", "body": "B", "category_ids": [category_id]},
            headers=admin_headers(student_token),
        )
        q1_id = r.json()["id"]
        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions",
            json={"title": "Q2", "body": "B", "category_ids": [category_id]},
            headers=admin_headers(student_token),
        )
        q2_id = r.json()["id"]

        r = httpx.post(
            f"{base_url}/api/courses/{course_id}/questions/{q1_id}/posts",
            json={"kind": "ANSWER", "body": "answer to Q1"},
            headers=admin_headers(staff_token),
        )
        q1_post_id = r.json()["posts"][-1]["id"]

        r = httpx.patch(
            f"{base_url}/api/courses/{course_id}/questions/{q2_id}/posts/{q1_post_id}/accept",
            json={"is_accepted": True},
            headers=admin_headers(staff_token),
        )
        assert r.status_code == 404


class TestUploadSizeCap:
    def test_oversized_staff_csv_is_rejected(self, base_url, course_id, admin_token):
        oversized = "netid,full_name,email\n" + ("a" * (3 * 1024 * 1024))  # > 2 MB cap
        files = {"file": ("staff.csv", oversized, "text/csv")}
        r = httpx.post(
            f"{base_url}/api/admin/courses/{course_id}/staff",
            files=files,
            headers=admin_headers(admin_token),
            timeout=15,
        )
        assert r.status_code == 413
