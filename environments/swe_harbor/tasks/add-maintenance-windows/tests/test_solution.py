"""Tests for the Check Maintenance Windows feature."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Check
from hc.test import BaseTestCase


class MaintenanceWindowModelTestCase(BaseTestCase):
    """Tests for the MaintenanceWindow model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_maintenance_window_model_exists(self):
        from hc.api.models import MaintenanceWindow
        self.assertTrue(hasattr(MaintenanceWindow, "objects"))

    def test_create_maintenance_window(self):
        from hc.api.models import MaintenanceWindow
        start = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 2, 1, 16, 0, 0, tzinfo=timezone.utc)
        w = MaintenanceWindow.objects.create(
            owner=self.check, start=start, end=end, reason="Server upgrade"
        )
        self.assertIsNotNone(w.code)
        self.assertEqual(w.reason, "Server upgrade")

    def test_to_dict(self):
        from hc.api.models import MaintenanceWindow
        start = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        w = MaintenanceWindow.objects.create(owner=self.check, start=start, reason="Upgrade")
        d = w.to_dict()
        self.assertIn("uuid", d)
        self.assertIn("start", d)
        self.assertIn("end", d)
        self.assertEqual(d["reason"], "Upgrade")

    def test_ordering(self):
        from hc.api.models import MaintenanceWindow
        start1 = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
        start2 = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        MaintenanceWindow.objects.create(owner=self.check, start=start1, reason="First")
        MaintenanceWindow.objects.create(owner=self.check, start=start2, reason="Second")
        windows = list(MaintenanceWindow.objects.filter(owner=self.check))
        self.assertEqual(windows[0].reason, "Second")
        self.assertEqual(windows[1].reason, "First")

    def test_cascade_delete(self):
        from hc.api.models import MaintenanceWindow
        start = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        MaintenanceWindow.objects.create(owner=self.check, start=start, reason="Gone")
        self.check.delete()
        self.assertEqual(MaintenanceWindow.objects.count(), 0)


class CreateMaintenanceWindowApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/maintenance/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/maintenance/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_create_window(self):
        r = self.post({"start": "2025-02-01T14:00:00+00:00", "reason": "Upgrade"})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertIn("uuid", doc)
        self.assertIn("start", doc)
        self.assertEqual(doc["reason"], "Upgrade")

    def test_create_with_end(self):
        r = self.post({
            "start": "2025-02-01T14:00:00+00:00",
            "end": "2025-02-01T16:00:00+00:00",
            "reason": "Window",
        })
        self.assertEqual(r.status_code, 201)
        self.assertIn("end", r.json())

    def test_missing_start(self):
        r = self.post({"reason": "No start"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("start", r.json()["error"].lower())

    def test_invalid_start(self):
        r = self.post({"start": "not-a-datetime"})
        self.assertEqual(r.status_code, 400)

    def test_end_before_start(self):
        r = self.post({
            "start": "2025-02-01T16:00:00+00:00",
            "end": "2025-02-01T14:00:00+00:00",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("end", r.json()["error"].lower())

    def test_reason_too_long(self):
        r = self.post({"start": "2025-02-01T14:00:00+00:00", "reason": "x" * 201})
        self.assertEqual(r.status_code, 400)

    def test_wrong_project(self):
        other = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other.code}/maintenance/"
        r = self.client.post(
            url,
            json.dumps({"start": "2025-02-01T14:00:00+00:00", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        url = f"/api/v3/checks/{uuid.uuid4()}/maintenance/"
        r = self.client.post(
            url,
            json.dumps({"start": "2025-02-01T14:00:00+00:00", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)


class ListMaintenanceWindowsApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/maintenance/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/maintenance/"

    def get(self, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.get(self.url, HTTP_X_API_KEY=api_key)

    def test_list_empty(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["maintenance_windows"], [])

    def test_list_windows(self):
        from hc.api.models import MaintenanceWindow
        start = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        MaintenanceWindow.objects.create(owner=self.check, start=start, reason="One")
        MaintenanceWindow.objects.create(owner=self.check, start=start, reason="Two")
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["maintenance_windows"]), 2)

    def test_wrong_api_key(self):
        r = self.get(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_nonexistent_check(self):
        url = f"/api/v3/checks/{uuid.uuid4()}/maintenance/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)


class CheckToDictMaintenanceWindowsTestCase(BaseTestCase):
    """Tests for maintenance_windows_count in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_count_zero(self):
        d = self.check.to_dict()
        self.assertIn("maintenance_windows_count", d)
        self.assertEqual(d["maintenance_windows_count"], 0)

    def test_count_reflects_actual(self):
        from hc.api.models import MaintenanceWindow
        start = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        MaintenanceWindow.objects.create(owner=self.check, start=start, reason="A")
        MaintenanceWindow.objects.create(owner=self.check, start=start, reason="B")
        d = self.check.to_dict()
        self.assertEqual(d["maintenance_windows_count"], 2)


class MaintenanceWindowUrlRoutingTestCase(BaseTestCase):
    """Tests for URL routing (v1/v2/v3)."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_v1_endpoint(self):
        url = f"/api/v1/checks/{self.check.code}/maintenance/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v2_endpoint(self):
        url = f"/api/v2/checks/{self.check.code}/maintenance/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v3_endpoint(self):
        url = f"/api/v3/checks/{self.check.code}/maintenance/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_options_request(self):
        url = f"/api/v3/checks/{self.check.code}/maintenance/"
        r = self.client.options(url)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
