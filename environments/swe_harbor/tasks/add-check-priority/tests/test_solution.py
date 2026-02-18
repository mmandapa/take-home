"""Tests for the Check priority feature (36 tests)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
import django
django.setup()

from hc.api.models import Check
from hc.test import BaseTestCase


class PriorityModelTestCase(BaseTestCase):
    """Check model has priority field, default, and to_dict includes it."""

    def test_check_has_priority_field(self):
        self.assertTrue(hasattr(Check, "priority"))

    def test_default_priority_is_one(self):
        c = Check.objects.create(project=self.project, name="D")
        self.assertEqual(c.priority, 1)

    def test_to_dict_includes_priority(self):
        c = Check.objects.create(project=self.project, name="Dict", priority=2)
        d = c.to_dict(v=3)
        self.assertIn("priority", d)
        self.assertEqual(d["priority"], 2)

    def test_to_dict_priority_default(self):
        c = Check.objects.create(project=self.project, name="Def")
        d = c.to_dict(v=3)
        self.assertEqual(d["priority"], 1)

    def test_priority_zero_low(self):
        c = Check.objects.create(project=self.project, name="Low", priority=0)
        self.assertEqual(c.priority, 0)
        self.assertEqual(c.to_dict(v=3)["priority"], 0)

    def test_priority_two_high(self):
        c = Check.objects.create(project=self.project, name="High", priority=2)
        self.assertEqual(c.priority, 2)

    def test_to_dict_v1_includes_priority(self):
        c = Check.objects.create(project=self.project, name="V1", priority=1)
        d = c.to_dict(v=1)
        self.assertIn("priority", d)
        self.assertEqual(d["priority"], 1)

    def test_to_dict_v2_includes_priority(self):
        c = Check.objects.create(project=self.project, name="V2", priority=2)
        d = c.to_dict(v=2)
        self.assertIn("priority", d)


class CreateWithPriorityTestCase(BaseTestCase):
    """Create check with priority via API."""

    def post_create(self, data=None):
        data = data or {}
        if "api_key" not in data:
            data["api_key"] = "X" * 32
        return self.client.post(
            "/api/v3/checks/",
            json.dumps(data),
            content_type="application/json",
        )

    def test_create_with_priority_high(self):
        r = self.post_create({"name": "Important", "priority": 2})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["priority"], 2)

    def test_create_with_priority_low(self):
        r = self.post_create({"name": "Back burner", "priority": 0})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["priority"], 0)

    def test_create_omit_priority_gets_default(self):
        r = self.post_create({"name": "No priority"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["priority"], 1)

    def test_create_with_priority_normal_explicit(self):
        r = self.post_create({"name": "Normal", "priority": 1})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["priority"], 1)


class UpdatePriorityTestCase(BaseTestCase):
    """Update check priority via API."""

    def post_update(self, code, data, api_key="X" * 32):
        return self.client.post(
            f"/api/v3/checks/{code}",
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_update_priority_from_default_to_high(self):
        c = Check.objects.create(project=self.project, name="Up", priority=1)
        r = self.post_update(str(c.code), {"priority": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 2)
        c.refresh_from_db()
        self.assertEqual(c.priority, 2)

    def test_update_priority_to_low(self):
        c = Check.objects.create(project=self.project, name="Down", priority=2)
        r = self.post_update(str(c.code), {"priority": 0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 0)

    def test_update_other_field_preserves_priority(self):
        c = Check.objects.create(project=self.project, name="Preserve", priority=2)
        r = self.post_update(str(c.code), {"name": "Preserved"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 2)

    def test_update_omit_priority_preserves_existing(self):
        c = Check.objects.create(project=self.project, name="Keep", priority=2)
        r = self.post_update(str(c.code), {"name": "Kept"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 2)
        c.refresh_from_db()
        self.assertEqual(c.priority, 2)

    def test_update_priority_to_normal_explicit(self):
        c = Check.objects.create(project=self.project, name="Norm", priority=0)
        r = self.post_update(str(c.code), {"priority": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 1)


class ListOrderingTestCase(BaseTestCase):
    """GET /api/v*/checks/ returns checks ordered by priority desc, then name."""

    def get_list(self, v=3):
        return self.client.get(f"/api/v{v}/checks/", HTTP_X_API_KEY="X" * 32)

    def test_order_high_before_low(self):
        Check.objects.create(project=self.project, name="Low", priority=0)
        Check.objects.create(project=self.project, name="High", priority=2)
        Check.objects.create(project=self.project, name="Mid", priority=1)
        r = self.get_list()
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 3)
        self.assertEqual(checks[0]["priority"], 2)
        self.assertEqual(checks[0]["name"], "High")
        self.assertEqual(checks[1]["priority"], 1)
        self.assertEqual(checks[2]["priority"], 0)

    def test_same_priority_ordered_by_name(self):
        Check.objects.create(project=self.project, name="Zebra", priority=1)
        Check.objects.create(project=self.project, name="Alpha", priority=1)
        Check.objects.create(project=self.project, name="Middle", priority=1)
        r = self.get_list()
        self.assertEqual(r.status_code, 200)
        names = [c["name"] for c in r.json()["checks"]]
        self.assertEqual(names, ["Alpha", "Middle", "Zebra"])

    def test_order_mixed_priority_and_name(self):
        Check.objects.create(project=self.project, name="A", priority=1)
        Check.objects.create(project=self.project, name="B", priority=2)
        Check.objects.create(project=self.project, name="C", priority=0)
        r = self.get_list()
        order = [(c["priority"], c["name"]) for c in r.json()["checks"]]
        self.assertEqual(order, [(2, "B"), (1, "A"), (0, "C")])

    def test_list_v1_ordering(self):
        Check.objects.create(project=self.project, name="X", priority=0)
        Check.objects.create(project=self.project, name="Y", priority=2)
        r = self.client.get("/api/v1/checks/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(checks[0]["priority"], 2)

    def test_list_v2_ordering(self):
        Check.objects.create(project=self.project, name="V2a", priority=1)
        Check.objects.create(project=self.project, name="V2b", priority=2)
        r = self.client.get("/api/v2/checks/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["checks"][0]["priority"], 2)

    def test_empty_list_returns_empty_checks(self):
        r = self.get_list()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["checks"], [])

    def test_five_checks_ordered_priority_then_name(self):
        for name, pri in [("A", 0), ("B", 2), ("C", 1), ("D", 2), ("E", 0)]:
            Check.objects.create(project=self.project, name=name, priority=pri)
        r = self.get_list()
        order = [(c["priority"], c["name"]) for c in r.json()["checks"]]
        self.assertEqual(order, [(2, "B"), (2, "D"), (1, "C"), (0, "A"), (0, "E")])


class GetSingleCheckPriorityTestCase(BaseTestCase):
    """GET single check returns priority."""

    def test_get_single_returns_priority(self):
        c = Check.objects.create(project=self.project, name="Single", priority=2)
        r = self.client.get(
            f"/api/v3/checks/{c.code}",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 2)

    def test_get_single_v1_returns_priority(self):
        c = Check.objects.create(project=self.project, name="V1s", priority=0)
        r = self.client.get(f"/api/v1/checks/{c.code}", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 0)

    def test_get_single_v2_returns_priority(self):
        c = Check.objects.create(project=self.project, name="V2s", priority=1)
        r = self.client.get(f"/api/v2/checks/{c.code}", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["priority"], 1)


class InvalidPriorityValidationTestCase(BaseTestCase):
    """Invalid priority in create/update returns 400."""

    def post_create(self, data):
        data = {**data, "api_key": "X" * 32}
        return self.client.post(
            "/api/v3/checks/",
            json.dumps(data),
            content_type="application/json",
        )

    def post_update(self, code, data):
        data = {**data, "api_key": "X" * 32}
        return self.client.post(
            f"/api/v3/checks/{code}",
            json.dumps(data),
            content_type="application/json",
        )

    def test_create_priority_above_two_returns_400(self):
        r = self.post_create({"name": "Bad", "priority": 3})
        self.assertEqual(r.status_code, 400)

    def test_create_priority_negative_returns_400(self):
        r = self.post_create({"name": "Bad", "priority": -1})
        self.assertEqual(r.status_code, 400)

    def test_update_invalid_priority_returns_400(self):
        c = Check.objects.create(project=self.project, name="C", priority=1)
        r = self.post_update(str(c.code), {"priority": 5})
        self.assertEqual(r.status_code, 400)

    def test_create_priority_four_returns_400(self):
        r = self.post_create({"name": "Bad", "priority": 4})
        self.assertEqual(r.status_code, 400)

    def test_create_priority_string_returns_400(self):
        r = self.post_create({"name": "Bad", "priority": "high"})
        self.assertEqual(r.status_code, 400)


class PriorityProjectScopingTestCase(BaseTestCase):
    """Priority list only includes current project's checks."""

    def test_list_only_current_project(self):
        Check.objects.create(project=self.project, name="Mine", priority=2)
        Check.objects.create(project=self.bobs_project, name="Bobs", priority=2)
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        names = [c["name"] for c in r.json()["checks"]]
        self.assertEqual(names, ["Mine"])
        self.assertNotIn("Bobs", names)


class ListChecksAuthTestCase(BaseTestCase):
    """Auth: wrong or missing API key returns 401."""

    def test_missing_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/")
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_short_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="short")
        self.assertEqual(r.status_code, 401)
