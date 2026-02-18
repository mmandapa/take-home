"""Tests for the Check Clone API feature."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta as td

from django.test import TestCase
from django.utils.timezone import now

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Channel, Check, Ping
from hc.accounts.models import Project
from hc.test import BaseTestCase


class CloneLogModelTestCase(BaseTestCase):
    """Tests for the CloneLog model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Source Check")
        self.other_check = Check.objects.create(project=self.project, name="Cloned Check")

    def test_create_clone_log(self):
        """Can create a CloneLog entry."""
        from hc.api.models import CloneLog
        log = CloneLog.objects.create(
            source_check=self.check,
            cloned_check=self.other_check,
            target_project=self.project,
            cloned_by="alice@example.org",
        )
        self.assertIsNotNone(log.code)
        self.assertEqual(log.cloned_by, "alice@example.org")

    def test_to_dict(self):
        """to_dict() returns correct keys and values."""
        from hc.api.models import CloneLog
        log = CloneLog.objects.create(
            source_check=self.check,
            cloned_check=self.other_check,
            target_project=self.bobs_project,
            cloned_by="alice@example.org",
        )
        d = log.to_dict()
        self.assertEqual(d["uuid"], str(log.code))
        self.assertEqual(d["source_check"], str(self.check.code))
        self.assertEqual(d["cloned_check"], str(self.other_check.code))
        self.assertEqual(d["target_project"], str(self.bobs_project.code))
        self.assertEqual(d["cloned_by"], "alice@example.org")
        self.assertIn("created", d)
        self.assertIsInstance(d["created"], str)
        self.assertNotRegex(d["created"], r"\.\d{6}", msg="created should be ISO without microseconds")

    def test_ordering(self):
        """CloneLog entries should be ordered newest first."""
        from hc.api.models import CloneLog
        third = Check.objects.create(project=self.project, name="Third")
        log1 = CloneLog.objects.create(
            source_check=self.check,
            cloned_check=self.other_check,
            target_project=self.project,
        )
        log1.created = now() - td(hours=1)
        log1.save(update_fields=["created"])
        log2 = CloneLog.objects.create(
            source_check=self.check,
            cloned_check=third,
            target_project=self.project,
        )
        logs = list(CloneLog.objects.filter(source_check=self.check))
        self.assertEqual(logs[0].id, log2.id)
        self.assertEqual(logs[1].id, log1.id)

    def test_cascade_delete_source(self):
        """Deleting the source check deletes its clone log entries."""
        from hc.api.models import CloneLog
        CloneLog.objects.create(
            source_check=self.check,
            cloned_check=self.other_check,
            target_project=self.project,
        )
        self.assertEqual(CloneLog.objects.filter(source_check=self.check).count(), 1)
        source_id = self.check.id
        self.check.delete()
        self.assertEqual(CloneLog.objects.filter(source_check_id=source_id).count(), 0)

    def test_cascade_delete_cloned(self):
        """Deleting the cloned check deletes the clone log entry."""
        from hc.api.models import CloneLog
        CloneLog.objects.create(
            source_check=self.check,
            cloned_check=self.other_check,
            target_project=self.project,
        )
        cloned_id = self.other_check.id
        self.other_check.delete()
        self.assertEqual(CloneLog.objects.filter(cloned_check_id=cloned_id).count(), 0)


class CheckCloneMethodTestCase(BaseTestCase):
    """Tests for the Check.clone() method."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(
            project=self.project,
            name="Clone Me",
            slug="clone-me",
            tags="foo bar",
            desc="A check",
            status="up",
            n_pings=5,
        )
        self.check.last_ping = now()
        self.check.save()
        self.target_channel = Channel.objects.create(
            project=self.bobs_project, kind="email", value="bob@example.org"
        )

    def test_clone_creates_new_check(self):
        """clone() should create a new check in the target project."""
        new_check = self.check.clone(self.bobs_project)
        self.assertIsNotNone(new_check.id)
        self.assertNotEqual(new_check.id, self.check.id)
        self.assertNotEqual(new_check.code, self.check.code)
        self.assertEqual(new_check.project_id, self.bobs_project.id)

    def test_clone_copies_config_fields(self):
        """clone() should copy name, slug, tags, desc, kind, timeout, grace, etc."""
        new_check = self.check.clone(self.bobs_project)
        self.assertEqual(new_check.name, "Clone Me")
        self.assertEqual(new_check.slug, "clone-me")
        self.assertEqual(new_check.tags, "foo bar")
        self.assertEqual(new_check.desc, "A check")
        self.assertEqual(new_check.kind, self.check.kind)
        self.assertEqual(new_check.timeout, self.check.timeout)
        self.assertEqual(new_check.grace, self.check.grace)
        self.assertEqual(new_check.schedule, self.check.schedule)
        self.assertEqual(new_check.tz, self.check.tz)
        self.assertEqual(new_check.filter_subject, self.check.filter_subject)
        self.assertEqual(new_check.filter_body, self.check.filter_body)
        self.assertEqual(new_check.methods, self.check.methods)
        self.assertEqual(new_check.manual_resume, self.check.manual_resume)

    def test_clone_copies_cron_schedule_and_tz(self):
        """clone() should copy kind, schedule, tz for cron/oncalendar checks."""
        self.check.kind = "cron"
        self.check.schedule = "0 12 * * *"
        self.check.tz = "Europe/London"
        self.check.save()
        new_check = self.check.clone(self.bobs_project)
        self.assertEqual(new_check.kind, "cron")
        self.assertEqual(new_check.schedule, "0 12 * * *")
        self.assertEqual(new_check.tz, "Europe/London")

    def test_clone_uses_default_state(self):
        """clone() should not copy n_pings, last_ping, status; use defaults."""
        new_check = self.check.clone(self.bobs_project)
        self.assertEqual(new_check.n_pings, 0)
        self.assertIsNone(new_check.last_ping)
        self.assertEqual(new_check.status, "new")

    def test_clone_name_override(self):
        """clone() should use name_override when provided."""
        new_check = self.check.clone(self.bobs_project, name_override="New Name")
        self.assertEqual(new_check.name, "New Name")

    def test_clone_assigns_target_channels(self):
        """clone() should assign target project's channels to the new check."""
        new_check = self.check.clone(self.bobs_project)
        channels = list(new_check.channel_set.all())
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0].id, self.target_channel.id)

    def test_clone_creates_clonelog(self):
        """clone() should create a CloneLog entry."""
        from hc.api.models import CloneLog
        new_check = self.check.clone(self.bobs_project, cloned_by="alice@example.org")
        logs = CloneLog.objects.filter(source_check=self.check)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.cloned_check_id, new_check.id)
        self.assertEqual(log.target_project_id, self.bobs_project.id)
        self.assertEqual(log.cloned_by, "alice@example.org")

    def test_clone_same_project(self):
        """clone() to same project should work."""
        new_check = self.check.clone(self.project)
        self.assertEqual(new_check.project_id, self.project.id)
        self.assertNotEqual(new_check.code, self.check.code)

    def test_clone_same_project_assigns_project_channels(self):
        """When cloning to same project, new check should get that project's channels."""
        ch = Channel.objects.create(project=self.project, kind="email", value="same@example.org")
        new_check = self.check.clone(self.project)
        channels = list(new_check.channel_set.all())
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0].id, ch.id)

    def test_clone_raises_on_no_capacity(self):
        """clone() should raise ValueError if target has no capacity."""
        from hc.accounts.models import Profile
        profile = Profile.objects.for_user(self.bob)
        profile.check_limit = 1
        profile.save()
        Check.objects.create(project=self.bobs_project, name="Filler")

        with self.assertRaises(ValueError) as ctx:
            self.check.clone(self.bobs_project)
        self.assertIn("no checks available", str(ctx.exception))


class CloneApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/clone/"""

    def setUp(self):
        super().setUp()
        self.bobs_project.api_key = "B" * 32
        self.bobs_project.save()
        self.check = Check.objects.create(project=self.project, name="Clone Me")
        self.url = f"/api/v3/checks/{self.check.code}/clone/"

    def post(self, data, api_key=None, target_api_key=None):
        if api_key is None:
            api_key = "X" * 32
        payload = {**data, "api_key": api_key}
        if target_api_key is not None:
            payload["target_api_key"] = target_api_key
        return self.client.post(
            self.url,
            json.dumps(payload),
            content_type="application/json",
        )

    def test_clone_same_project_succeeds(self):
        """POST without project should clone to same project and return 201."""
        r = self.post({})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertIn("uuid", doc)
        self.assertNotEqual(doc["uuid"], str(self.check.code))
        self.assertEqual(doc["name"], "Clone Me")
        new_check = Check.objects.get(code=doc["uuid"])
        self.assertEqual(new_check.status, "new")
        self.assertEqual(new_check.n_pings, 0)

    def test_clone_other_project_succeeds(self):
        """POST with project and target_api_key should clone to other project."""
        r = self.post({"project": str(self.bobs_project.code), "target_api_key": "B" * 32})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertNotEqual(doc["uuid"], str(self.check.code))
        new_check = Check.objects.get(code=doc["uuid"])
        self.assertEqual(new_check.project_id, self.bobs_project.id)

    def test_clone_name_override(self):
        """POST with name should set the new check's name."""
        r = self.post({"name": "Custom Name"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["name"], "Custom Name")

    def test_invalid_project_uuid(self):
        """POST with invalid project UUID should return 400."""
        r = self.post({"project": "not-a-uuid"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid project uuid", r.json()["error"])

    def test_other_project_without_target_api_key(self):
        """POST to other project without target_api_key should return 403."""
        r = self.post({"project": str(self.bobs_project.code)})
        self.assertEqual(r.status_code, 403)
        self.assertIn("not authorized", r.json()["error"])

    def test_other_project_wrong_target_api_key(self):
        """POST to other project with wrong target_api_key should return 403."""
        r = self.post(
            {"project": str(self.bobs_project.code)},
            target_api_key="Z" * 32,
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("not authorized", r.json()["error"])

    def test_same_project_with_target_api_key(self):
        """POST to same project but with target_api_key should return 400."""
        r = self.post({"project": str(self.project.code), "target_api_key": "X" * 32})
        self.assertEqual(r.status_code, 400)
        self.assertIn("same project", r.json()["error"])

    def test_no_capacity(self):
        """POST when target project has no capacity should return 400."""
        from hc.accounts.models import Profile
        profile = Profile.objects.for_user(self.bob)
        profile.check_limit = 1
        profile.save()
        Check.objects.create(project=self.bobs_project, name="Filler")
        r = self.post({"project": str(self.bobs_project.code), "target_api_key": "B" * 32})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no checks available", r.json()["error"])

    def test_wrong_api_key(self):
        """POST with wrong API key should return 401."""
        r = self.post({}, api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_wrong_project(self):
        """POST for check in different project should return 403."""
        other_check = Check.objects.create(project=self.charlies_project, name="Other")
        url = f"/api/v3/checks/{other_check.code}/clone/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """POST for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/clone/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_cloned_from_in_get_checks_response(self):
        """GET /checks/ response should include cloned_from for a cloned check."""
        r = self.post({})
        new_uuid = r.json()["uuid"]
        r2 = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="X" * 32)
        cloned = next(c for c in r2.json()["checks"] if c["uuid"] == new_uuid)
        self.assertIn("cloned_from", cloned)
        self.assertEqual(cloned["cloned_from"], str(self.check.code))


class ClonesHistoryApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/clones/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/clones/"

    def test_list_empty(self):
        """GET should return empty list when no clones."""
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["clones"], [])

    def test_list_clones(self):
        """GET should return clone log entries."""
        from hc.api.models import CloneLog
        other = Check.objects.create(project=self.project, name="Cloned")
        CloneLog.objects.create(
            source_check=self.check,
            cloned_check=other,
            target_project=self.project,
            cloned_by="alice@example.org",
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        clones = r.json()["clones"]
        self.assertEqual(len(clones), 1)
        self.assertEqual(clones[0]["cloned_by"], "alice@example.org")
        self.assertEqual(clones[0]["source_check"], str(self.check.code))
        self.assertEqual(clones[0]["cloned_check"], str(other.code))

    def test_list_clones_ordered_newest_first(self):
        """GET /clones/ should return entries ordered newest first."""
        from hc.api.models import CloneLog
        other1 = Check.objects.create(project=self.project, name="Cloned1")
        other2 = Check.objects.create(project=self.project, name="Cloned2")
        log1 = CloneLog.objects.create(
            source_check=self.check,
            cloned_check=other1,
            target_project=self.project,
        )
        log1.created = now() - td(hours=1)
        log1.save(update_fields=["created"])
        CloneLog.objects.create(
            source_check=self.check,
            cloned_check=other2,
            target_project=self.project,
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        clones = r.json()["clones"]
        self.assertEqual(len(clones), 2)
        self.assertEqual(clones[0]["cloned_check"], str(other2.code))
        self.assertEqual(clones[1]["cloned_check"], str(other1.code))

    def test_list_doesnt_include_other_checks_clones(self):
        """GET /clones/ must filter by source_check; other checks' clone logs must not appear."""
        from hc.api.models import CloneLog
        other_source = Check.objects.create(project=self.project, name="Other Source")
        other_clone = Check.objects.create(project=self.project, name="Other Clone")
        CloneLog.objects.create(
            source_check=other_source,
            cloned_check=other_clone,
            target_project=self.project,
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["clones"], [])

    def test_wrong_project(self):
        """GET for check in different project should return 403."""
        other_check = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other_check.code}/clones/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """GET for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/clones/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_wrong_api_key(self):
        """GET with wrong API key should return 401."""
        r = self.client.get(self.url, HTTP_X_API_KEY="Y" * 32)
        self.assertEqual(r.status_code, 401)


class CheckToDictClonedFromTestCase(BaseTestCase):
    """Tests for cloned_from in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Source")
        self.cloned = Check.objects.create(project=self.project, name="Cloned")

    def test_cloned_from_absent_when_not_cloned(self):
        """to_dict() should have cloned_from null when check was not cloned."""
        d = self.check.to_dict()
        self.assertIn("cloned_from", d)
        self.assertIsNone(d["cloned_from"])

    def test_cloned_from_set_via_clone_method(self):
        """clone() creates CloneLog so the new check's to_dict() has cloned_from set."""
        new_check = self.check.clone(self.project)
        d = new_check.to_dict()
        self.assertIn("cloned_from", d)
        self.assertEqual(d["cloned_from"], str(self.check.code))

    def test_cloned_by_populated_via_api(self):
        """POST clone should create CloneLog with cloned_by set (e.g. from request context)."""
        url = f"/api/v3/checks/{self.check.code}/clone/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        from hc.api.models import CloneLog
        logs = CloneLog.objects.filter(source_check=self.check)
        self.assertEqual(logs.count(), 1)
        self.assertIsInstance(logs.first().cloned_by, str)


class CloneUrlRoutingTestCase(BaseTestCase):
    """Tests for URL routing across API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test")

    def test_v3_clone_endpoint(self):
        """POST clone should work under /api/v3/."""
        r = self.client.post(
            f"/api/v3/checks/{self.check.code}/clone/",
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

    def test_v3_clones_endpoint(self):
        """GET clones should work under /api/v3/."""
        url = f"/api/v3/checks/{self.check.code}/clones/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_clone_cors(self):
        """Clone endpoint should return CORS headers."""
        url = f"/api/v3/checks/{self.check.code}/clones/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
