"""Tests for the Pause Reason feature."""
from __future__ import annotations

import json
import uuid

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Check
from hc.test import BaseTestCase


class CheckPauseReasonModelTestCase(BaseTestCase):
    """Tests for pause_reason field on Check."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_pause_reason_field_exists(self):
        self.assertTrue(hasattr(Check, "pause_reason"))
        self.assertEqual(self.check.pause_reason, "")

    def test_pause_reason_default_empty(self):
        d = self.check.to_dict()
        self.assertIn("pause_reason", d)
        self.assertEqual(d["pause_reason"], "")


class PauseWithReasonApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/pause with reason."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/pause"

    def post(self, data=None, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        payload = {"api_key": api_key}
        if data is not None:
            payload.update(data)
        return self.client.post(
            self.url,
            json.dumps(payload),
            content_type="application/json",
        )

    def test_pause_with_reason(self):
        r = self.post({"reason": "Holiday maintenance"})
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["status"], "paused")
        self.assertEqual(doc["pause_reason"], "Holiday maintenance")

    def test_pause_without_reason(self):
        r = self.post({})
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertEqual(doc["status"], "paused")
        self.assertEqual(doc["pause_reason"], "")

    def test_pause_with_empty_reason(self):
        r = self.post({"reason": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pause_reason"], "")

    def test_pause_reason_not_string(self):
        r = self.post({"reason": 123})
        self.assertEqual(r.status_code, 400)
        self.assertIn("reason", r.json()["error"].lower())
        self.assertIn("string", r.json()["error"].lower())

    def test_pause_reason_too_long(self):
        r = self.post({"reason": "x" * 201})
        self.assertEqual(r.status_code, 400)
        self.assertIn("long", r.json()["error"].lower())

    def test_pause_reason_max_length_ok(self):
        r = self.post({"reason": "x" * 200})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pause_reason"], "x" * 200)

    def test_wrong_project(self):
        other = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other.code}/pause"
        r = self.client.post(
            url,
            json.dumps({"reason": "nope", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        url = f"/api/v3/checks/{uuid.uuid4()}/pause"
        r = self.client.post(
            url,
            json.dumps({"reason": "nope", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_pause_reason_null_returns_400(self):
        r = self.post({"reason": None})
        self.assertEqual(r.status_code, 400)
        self.assertIn("reason", r.json()["error"].lower())
        self.assertIn("string", r.json()["error"].lower())

    def test_pause_twice_updates_reason(self):
        r1 = self.post({"reason": "First reason"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["pause_reason"], "First reason")
        r2 = self.post({"reason": "Updated reason"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["pause_reason"], "Updated reason")


class ResumeClearsReasonTestCase(BaseTestCase):
    """Tests that resume clears pause_reason."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.pause_url = f"/api/v3/checks/{self.check.code}/pause"
        self.resume_url = f"/api/v3/checks/{self.check.code}/resume"

    def test_resume_clears_reason(self):
        # Pause with reason
        r1 = self.client.post(
            self.pause_url,
            json.dumps({"reason": "Maintenance", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["pause_reason"], "Maintenance")
        # Resume
        r2 = self.client.post(
            self.resume_url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "new")
        self.assertEqual(r2.json()["pause_reason"], "")

    def test_resume_when_not_paused(self):
        r = self.client.post(
            self.resume_url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)

    def test_resume_response_includes_pause_reason(self):
        self.client.post(
            self.pause_url,
            json.dumps({"reason": "Before resume", "api_key": "X" * 32}),
            content_type="application/json",
        )
        r = self.client.post(
            self.resume_url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("pause_reason", r.json())
        self.assertEqual(r.json()["pause_reason"], "")


class CheckToDictPauseReasonTestCase(BaseTestCase):
    """Tests for pause_reason in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_to_dict_includes_pause_reason(self):
        d = self.check.to_dict()
        self.assertIn("pause_reason", d)
        self.assertEqual(d["pause_reason"], "")

    def test_to_dict_after_pause_with_reason(self):
        self.check.status = "paused"
        self.check.pause_reason = "Holiday"
        self.check.save()
        d = self.check.to_dict()
        self.assertEqual(d["pause_reason"], "Holiday")


class PauseResumeUrlRoutingTestCase(BaseTestCase):
    """Tests for pause/resume URL routing (v1/v2/v3)."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_pause_v1(self):
        url = f"/api/v1/checks/{self.check.code}/pause"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("pause_reason", r.json())

    def test_pause_v2(self):
        url = f"/api/v2/checks/{self.check.code}/pause"
        r = self.client.post(
            url,
            json.dumps({"reason": "v2", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pause_reason"], "v2")

    def test_pause_v3(self):
        url = f"/api/v3/checks/{self.check.code}/pause"
        r = self.client.post(
            url,
            json.dumps({"reason": "v3", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pause_reason"], "v3")

    def test_resume_v3(self):
        # Pause first
        self.client.post(
            f"/api/v3/checks/{self.check.code}/pause",
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        url = f"/api/v3/checks/{self.check.code}/resume"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pause_reason"], "")
