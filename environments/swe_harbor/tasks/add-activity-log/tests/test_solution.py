"""Tests for the Activity Log feature (~35 tests with edge case coverage)."""
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


class ActivityLogModelTestCase(BaseTestCase):
    """Tests for the ActivityLog model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_activity_log_model_exists(self):
        from hc.api.models import ActivityLog
        self.assertTrue(hasattr(ActivityLog, "objects"))

    def test_create_activity_log(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "My check")
        self.assertEqual(ActivityLog.objects.filter(project=self.project).count(), 1)

    def test_to_dict_has_required_fields(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_updated", self.check.code, "details")
        rec = ActivityLog.objects.get(project=self.project)
        d = rec.to_dict()
        self.assertIn("action", d)
        self.assertIn("check_code", d)
        self.assertIn("details", d)
        self.assertIn("created", d)
        self.assertEqual(d["action"], "check_updated")
        self.assertEqual(d["check_code"], str(self.check.code))
        self.assertEqual(d["details"], "details")

    def test_to_dict_check_code_none_when_not_set(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "other", None, "")
        rec = ActivityLog.objects.get(project=self.project)
        d = rec.to_dict()
        self.assertIsNone(d["check_code"])

    def test_to_dict_details_empty_string(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_paused", self.check.code, "")
        rec = ActivityLog.objects.get(project=self.project)
        d = rec.to_dict()
        self.assertEqual(d["details"], "")

    def test_to_dict_created_iso8601_no_microseconds(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "")
        rec = ActivityLog.objects.get(project=self.project)
        d = rec.to_dict()
        self.assertNotIn(".", d["created"], "created must be ISO 8601 without microseconds")

    def test_to_dict_created_is_string_and_not_none(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "")
        rec = ActivityLog.objects.get(project=self.project)
        d = rec.to_dict()
        self.assertIsInstance(d["created"], str)
        self.assertIsNotNone(d["created"])

    def test_ordering_newest_first(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "first")
        ActivityLog.log(self.project, "check_updated", self.check.code, "second")
        recs = list(ActivityLog.objects.filter(project=self.project))
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0].details, "second")
        self.assertEqual(recs[1].details, "first")

    def test_log_truncates_details_over_500_chars(self):
        from hc.api.models import ActivityLog
        long_details = "x" * 600
        ActivityLog.log(self.project, "check_updated", self.check.code, long_details)
        rec = ActivityLog.objects.get(project=self.project)
        self.assertLessEqual(len(rec.details), 500)
        d = rec.to_dict()
        self.assertLessEqual(len(d["details"]), 500)

    def test_cascade_delete_activity_logs_when_project_deleted(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "gone")
        self.assertEqual(ActivityLog.objects.filter(project=self.project).count(), 1)
        self.project.delete()
        self.assertEqual(ActivityLog.objects.count(), 0)


class ActivityListEndpointTestCase(BaseTestCase):
    """Tests for GET /api/v3/activity/."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="List Test Check")

    def get_activity(self, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.get("/api/v3/activity/", HTTP_X_API_KEY=api_key)

    def test_list_empty_returns_200_and_shape(self):
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertIn("activity", doc)
        self.assertIsInstance(doc["activity"], list)
        self.assertEqual(len(doc["activity"]), 0)

    def test_list_with_write_key_returns_200(self):
        Check.objects.create(project=self.project, name="C1")
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertIn("activity", doc)

    def test_list_with_readonly_key_returns_200(self):
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.get_activity(api_key="R" * 32)
        self.assertEqual(r.status_code, 200)
        doc = r.json()
        self.assertIn("activity", doc)

    def test_list_wrong_api_key_returns_401(self):
        r = self.get_activity(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_list_missing_api_key_returns_401(self):
        r = self.client.get("/api/v3/activity/")
        self.assertEqual(r.status_code, 401)

    def test_cors_options_returns_204_and_allow_get(self):
        r = self.client.options("/api/v3/activity/")
        self.assertEqual(r.status_code, 204)
        self.assertIn("GET", r.get("Access-Control-Allow-Methods", ""))

    def test_v1_v2_v3_activity_urls_all_work(self):
        for prefix in ["/api/v1/activity/", "/api/v2/activity/", "/api/v3/activity/"]:
            r = self.client.get(prefix, HTTP_X_API_KEY="X" * 32)
            self.assertEqual(r.status_code, 200, f"GET {prefix} should return 200")
            self.assertIn("activity", r.json())

    def test_list_response_content_type_is_json(self):
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/json", r.get("Content-Type", ""))

    def test_list_each_item_has_required_keys(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "d")
        self.check = Check.objects.create(project=self.project, name="C2")
        ActivityLog.log(self.project, "check_paused", self.check.code, "")
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 2)
        required = {"action", "check_code", "details", "created"}
        for item in activity:
            self.assertEqual(set(item.keys()), required, f"Item {item} should have exactly {required}")

    def test_list_returns_newest_first(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "oldest")
        ActivityLog.log(self.project, "check_updated", self.check.code, "middle")
        ActivityLog.log(self.project, "check_paused", self.check.code, "newest")
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 3)
        self.assertEqual(activity[0]["details"], "newest")
        self.assertEqual(activity[1]["details"], "middle")
        self.assertEqual(activity[2]["details"], "oldest")

    def test_list_api_key_too_short_returns_401(self):
        r = self.client.get("/api/v3/activity/", HTTP_X_API_KEY="short")
        self.assertEqual(r.status_code, 401)

    def test_list_activity_item_check_code_valid_uuid(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "")
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertIsInstance(activity[0]["check_code"], str)
        uuid.UUID(activity[0]["check_code"])

    def test_list_activity_item_created_parseable_iso8601(self):
        from hc.api.models import ActivityLog
        ActivityLog.log(self.project, "check_created", self.check.code, "")
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        parsed = datetime.fromisoformat(activity[0]["created"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed)


class ActivityInjectionTestCase(BaseTestCase):
    """Tests that activity is logged when checks are created/updated/paused/resumed."""

    def post_checks(self, data=None):
        data = data or {}
        if "api_key" not in data:
            data["api_key"] = "X" * 32
        return self.client.post(
            "/api/v3/checks/",
            json.dumps(data),
            content_type="application/json",
        )

    def post_single(self, code, data, api_key="X" * 32):
        return self.client.post(
            f"/api/v3/checks/{code}",
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def post_pause(self, code, api_key="X" * 32):
        return self.client.post(
            f"/api/v3/checks/{code}/pause",
            json.dumps({"api_key": api_key}),
            content_type="application/json",
        )

    def post_resume(self, code, api_key="X" * 32):
        return self.client.post(
            f"/api/v3/checks/{code}/resume",
            json.dumps({"api_key": api_key}),
            content_type="application/json",
        )

    def get_activity(self):
        return self.client.get("/api/v3/activity/", HTTP_X_API_KEY="X" * 32)

    def test_create_check_logs_check_created(self):
        r = self.post_checks({"name": "New Check"})
        self.assertEqual(r.status_code, 201)
        r = self.get_activity()
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["action"], "check_created")
        self.assertIsNotNone(activity[0]["check_code"])

    def test_update_check_logs_check_updated(self):
        r = self.post_checks({"name": "Original"})
        self.assertEqual(r.status_code, 201)
        code = r.json()["uuid"]
        r = self.post_single(code, {"name": "Updated"})
        self.assertEqual(r.status_code, 200)
        activity = self.get_activity().json()["activity"]
        self.assertGreaterEqual(len(activity), 2)
        actions = [a["action"] for a in activity]
        self.assertIn("check_updated", actions)
        self.assertIn("check_created", actions)

    def test_pause_logs_check_paused(self):
        check = Check.objects.create(project=self.project, name="PauseMe")
        r = self.post_pause(str(check.code))
        self.assertEqual(r.status_code, 200)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["action"], "check_paused")
        self.assertEqual(activity[0]["check_code"], str(check.code))

    def test_resume_logs_check_resumed(self):
        check = Check.objects.create(project=self.project, name="ResumeMe", status="paused")
        r = self.post_resume(str(check.code))
        self.assertEqual(r.status_code, 200)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["action"], "check_resumed")

    def test_full_flow_logs_all_four_actions(self):
        r = self.post_checks({"name": "Flow"})
        self.assertEqual(r.status_code, 201)
        code = r.json()["uuid"]
        self.post_single(code, {"name": "FlowUpdated"})
        self.post_pause(code)
        self.post_resume(code)
        activity = self.get_activity().json()["activity"]
        actions = [a["action"] for a in activity]
        self.assertIn("check_created", actions)
        self.assertIn("check_updated", actions)
        self.assertIn("check_paused", actions)
        self.assertIn("check_resumed", actions)

    def test_two_creates_two_check_created_entries_with_different_codes(self):
        r1 = self.post_checks({"name": "First"})
        r2 = self.post_checks({"name": "Second"})
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 2)
        codes = {a["check_code"] for a in activity}
        self.assertEqual(len(codes), 2)
        self.assertEqual([a["action"] for a in activity], ["check_created", "check_created"])

    def test_details_reflects_check_name_after_create(self):
        self.post_checks({"name": "My Cron Job"})
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["action"], "check_created")
        self.assertEqual(activity[0]["details"], "My Cron Job")

    def test_invalid_create_does_not_log(self):
        r = self.post_checks({"timeout": -1})
        self.assertEqual(r.status_code, 400)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 0)

    def test_update_validation_error_does_not_log(self):
        r = self.post_checks({"name": "Original"})
        self.assertEqual(r.status_code, 201)
        code = r.json()["uuid"]
        r = self.post_single(code, {"timeout": -100})
        self.assertEqual(r.status_code, 400)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["action"], "check_created")

    def test_resume_when_not_paused_returns_409_does_not_log(self):
        check = Check.objects.create(project=self.project, name="NotPaused", status="new")
        r = self.post_resume(str(check.code))
        self.assertEqual(r.status_code, 409)
        activity = self.get_activity().json()["activity"]
        self.assertEqual(len(activity), 0)

    def test_update_wrong_project_403_does_not_log(self):
        r = self.post_checks({"name": "Mine"})
        self.assertEqual(r.status_code, 201)
        code = r.json()["uuid"]
        self.charlies_project.api_key = "C" * 32
        self.charlies_project.save()
        r = self.client.post(
            f"/api/v3/checks/{code}",
            json.dumps({"name": "Hacked", "api_key": "C" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)
        r = self.get_activity()
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["details"], "Mine")

    def test_pause_twice_both_successful_logs_twice(self):
        check = Check.objects.create(project=self.project, name="P", status="new")
        self.post_pause(str(check.code))
        self.post_pause(str(check.code))
        activity = self.get_activity().json()["activity"]
        paused_count = sum(1 for a in activity if a["action"] == "check_paused")
        self.assertEqual(paused_count, 2)


class ActivityProjectIsolationTestCase(BaseTestCase):
    """Activity list is scoped to project."""

    def test_activity_from_other_project_not_visible(self):
        from hc.api.models import ActivityLog
        check_a = Check.objects.create(project=self.project, name="A")
        ActivityLog.log(self.project, "check_created", check_a.code, "in A")
        self.charlies_project.api_key = "C" * 32
        self.charlies_project.save()
        check_c = Check.objects.create(project=self.charlies_project, name="C")
        ActivityLog.log(self.charlies_project, "check_created", check_c.code, "in C")
        r = self.client.get("/api/v3/activity/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["details"], "in A")
        r = self.client.get("/api/v3/activity/", HTTP_X_API_KEY="C" * 32)
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["details"], "in C")

    def test_list_with_bob_project_sees_only_bob_activity(self):
        from hc.api.models import ActivityLog
        Check.objects.create(project=self.project, name="Alice Check")
        self.project.save()
        ActivityLog.log(self.project, "check_created", Check.objects.get(project=self.project).code, "alice")
        self.bobs_project.api_key = "B" * 32
        self.bobs_project.save()
        check_bob = Check.objects.create(project=self.bobs_project, name="Bob Check")
        ActivityLog.log(self.bobs_project, "check_created", check_bob.code, "bob")
        r = self.client.get("/api/v3/activity/", HTTP_X_API_KEY="B" * 32)
        self.assertEqual(r.status_code, 200)
        activity = r.json()["activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0]["details"], "bob")
