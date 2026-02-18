"""Tests for the Check Archival and Restore feature."""
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


class ArchiveLogModelTestCase(BaseTestCase):
    """Tests for the ArchiveLog model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_create_archive_log(self):
        """Can create an ArchiveLog entry."""
        from hc.api.models import ArchiveLog
        self.check.archived_at = now()
        self.check.save()
        log = ArchiveLog.objects.create(
            owner=self.check,
            action="archived",
            by="alice@example.org",
        )
        self.assertIsNotNone(log.code)
        self.assertEqual(log.action, "archived")
        self.assertEqual(log.by, "alice@example.org")

    def test_to_dict(self):
        """to_dict() returns correct keys and values."""
        from hc.api.models import ArchiveLog
        log = ArchiveLog.objects.create(owner=self.check, action="restored", by="bob@example.org")
        d = log.to_dict()
        self.assertEqual(d["uuid"], str(log.code))
        self.assertEqual(d["check"], str(self.check.code))
        self.assertEqual(d["action"], "restored")
        self.assertEqual(d["by"], "bob@example.org")
        self.assertIn("at", d)
        self.assertIsInstance(d["at"], str)
        self.assertIn("T", d["at"], msg="at should be ISO 8601 format")
        self.assertNotRegex(d["at"], r"\.\d{6}", msg="at should not contain microseconds")

    def test_ordering(self):
        """ArchiveLog entries should be ordered newest first."""
        from hc.api.models import ArchiveLog
        past = now() - td(hours=1)
        log1 = ArchiveLog.objects.create(owner=self.check, action="archived", by="")
        log1.at = past
        log1.save(update_fields=["at"])
        log2 = ArchiveLog.objects.create(owner=self.check, action="restored", by="")
        logs = list(ArchiveLog.objects.filter(owner=self.check))
        self.assertEqual(logs[0].id, log2.id)
        self.assertEqual(logs[1].id, log1.id)

    def test_cascade_delete_check_deletes_archive_logs(self):
        """Deleting a check should CASCADE delete its ArchiveLog entries."""
        from hc.api.models import ArchiveLog
        ArchiveLog.objects.create(owner=self.check, action="archived", by="")
        self.assertEqual(ArchiveLog.objects.filter(owner=self.check).count(), 1)
        check_id = self.check.id
        self.check.delete()
        self.assertEqual(ArchiveLog.objects.filter(owner_id=check_id).count(), 0)


class GetChecksArchivedFilterTestCase(BaseTestCase):
    """Tests for get_checks excluding/including archived."""

    def setUp(self):
        super().setUp()
        self.check_active = Check.objects.create(project=self.project, name="Active")
        self.check_archived = Check.objects.create(project=self.project, name="Archived")
        self.check_archived.archived_at = now()
        self.check_archived.save()

    def test_excludes_archived_by_default(self):
        """GET checks should exclude archived checks by default."""
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        codes = [c["uuid"] for c in checks]
        self.assertIn(str(self.check_active.code), codes)
        self.assertNotIn(str(self.check_archived.code), codes)

    def test_archived_param_returns_only_archived(self):
        """GET checks?archived=1 should return only archived checks."""
        r = self.client.get("/api/v3/checks/?archived=1", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        codes = [c["uuid"] for c in checks]
        self.assertNotIn(str(self.check_active.code), codes)
        self.assertIn(str(self.check_archived.code), codes)

    def test_archived_checks_list_includes_archived_check(self):
        """When implementation includes archived_at in check dict, it is non-null for archived checks."""
        r = self.client.get("/api/v3/checks/?archived=1", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        for c in checks:
            if c["uuid"] == str(self.check_archived.code):
                if "archived_at" in c:
                    self.assertIsNotNone(c["archived_at"], msg="archived_at should be set when key present")
                return
        self.fail("archived check should appear in ?archived=1 list")


class PingArchived410TestCase(BaseTestCase):
    """Tests for ping returning 410 when check is archived."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test", slug="test-ping")
        self.check.archived_at = now()
        self.check.save()

    def test_ping_by_code_returns_410_when_archived(self):
        """Ping by UUID should return 410 when check is archived; check.ping() must not be called."""
        n_before = self.check.n_pings
        last_ping_before = self.check.last_ping
        r = self.client.get(f"/ping/{self.check.code}")
        self.assertEqual(r.status_code, 410)
        self.check.refresh_from_db()
        self.assertEqual(self.check.n_pings, n_before, msg="ping() must not be called when archived")
        self.assertEqual(self.check.last_ping, last_ping_before)

    def test_ping_by_slug_returns_410_when_archived(self):
        """Ping by slug should return 410 when check is archived; check.ping() must not be called."""
        self.project.ping_key = "p" * 22
        self.project.save()
        n_before = self.check.n_pings
        r = self.client.get(f"/ping/{self.project.ping_key}/{self.check.slug}")
        self.assertEqual(r.status_code, 410)
        self.check.refresh_from_db()
        self.assertEqual(self.check.n_pings, n_before, msg="ping() must not be called when archived")

    def test_ping_returns_200_when_not_archived(self):
        """Ping should return 200 when check is not archived."""
        self.check.archived_at = None
        self.check.save()
        r = self.client.get(f"/ping/{self.check.code}")
        self.assertEqual(r.status_code, 200)


class ArchiveApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/archive/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="To Archive")
        self.url = f"/api/v3/checks/{self.check.code}/archive/"

    def post(self, data=None, api_key=None):
        if data is None:
            data = {}
        if api_key is None:
            api_key = "X" * 32
        payload = {**data, "api_key": api_key}
        return self.client.post(
            self.url,
            json.dumps(payload),
            content_type="application/json",
        )

    def test_archive_succeeds(self):
        """POST should archive the check and return 200."""
        r = self.post()
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertIsNotNone(self.check.archived_at)

    def test_archive_creates_archive_log(self):
        """POST archive should create an ArchiveLog entry with action=archived."""
        self.post()
        from hc.api.models import ArchiveLog
        self.assertEqual(ArchiveLog.objects.filter(owner=self.check, action="archived").count(), 1)

    def test_archive_stores_reason_in_log(self):
        """POST body reason should be stored in ArchiveLog.by."""
        r = self.post({"reason": "planned maintenance"})
        self.assertEqual(r.status_code, 200)
        from hc.api.models import ArchiveLog
        log = ArchiveLog.objects.get(owner=self.check, action="archived")
        self.assertEqual(log.by, "planned maintenance")

    def test_archive_returns_check_dict(self):
        """POST should return the check's to_dict()."""
        r = self.post()
        doc = r.json()
        self.assertIn("name", doc)
        self.assertEqual(doc["name"], "To Archive")

    def test_archive_already_archived_returns_400(self):
        """POST when already archived should return 400."""
        self.check.archived_at = now()
        self.check.save()
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertIn("already archived", r.json()["error"])

    def test_archive_wrong_project_returns_403(self):
        """POST for check in different project should return 403."""
        other = Check.objects.create(project=self.charlies_project, name="Other")
        url = f"/api/v3/checks/{other.code}/archive/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_archive_nonexistent_returns_404(self):
        """POST for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/archive/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_archive_readonly_key_returns_401(self):
        """POST archive with read-only API key should return 401 (write required)."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.post(api_key="R" * 32)
        self.assertEqual(r.status_code, 401)


class RestoreApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/restore/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="To Restore")
        self.check.archived_at = now()
        self.check.status = "up"
        self.check.n_pings = 5
        self.check.save()
        self.url = f"/api/v3/checks/{self.check.code}/restore/"

    def post(self, data=None, api_key=None):
        if data is None:
            data = {}
        if api_key is None:
            api_key = "X" * 32
        payload = {**data, "api_key": api_key}
        return self.client.post(
            self.url,
            json.dumps(payload),
            content_type="application/json",
        )

    def test_restore_succeeds(self):
        """POST should restore the check and return 200."""
        r = self.post()
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertIsNone(self.check.archived_at)
        self.assertEqual(self.check.status, "new")

    def test_restore_creates_archive_log(self):
        """POST restore should create an ArchiveLog entry with action=restored."""
        self.post()
        from hc.api.models import ArchiveLog
        self.assertEqual(ArchiveLog.objects.filter(owner=self.check, action="restored").count(), 1)

    def test_restore_readonly_key_returns_401(self):
        """POST restore with read-only API key should return 401 (write required)."""
        self.project.api_key_readonly = "R" * 32
        self.project.save()
        r = self.post(api_key="R" * 32)
        self.assertEqual(r.status_code, 401)

    def test_restore_clears_n_pings(self):
        """POST restore should reset n_pings and related state."""
        r = self.post()
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertEqual(self.check.n_pings, 0)
        self.assertIsNone(self.check.last_ping)
        self.assertIsNone(self.check.alert_after)

    def test_restore_not_archived_returns_400(self):
        """POST when check is not archived should return 400."""
        self.check.archived_at = None
        self.check.save()
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertIn("not archived", r.json()["error"])

    def test_restore_no_capacity_returns_400(self):
        """POST when project has no capacity should return 400."""
        from hc.accounts.models import Profile
        profile = Profile.objects.for_user(self.alice)
        profile.check_limit = 1
        profile.save()
        # Fill the single slot with a non-archived check so available=0 regardless of impl.
        Check.objects.create(project=self.project, name="Filler")
        r = self.post()
        self.assertEqual(r.status_code, 400)
        err = r.json().get("error", "")
        self.assertIn("no checks available", err, msg="error message should mention no checks available")

    def test_restore_wrong_project_returns_403(self):
        """POST for check in different project should return 403."""
        other = Check.objects.create(project=self.charlies_project, name="Other")
        other.archived_at = now()
        other.save()
        url = f"/api/v3/checks/{other.code}/restore/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_restore_nonexistent_returns_404(self):
        """POST for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/restore/"
        r = self.client.post(
            url,
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)


class ArchiveHistoryApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/archive-history/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test")
        self.url = f"/api/v3/checks/{self.check.code}/archive-history/"

    def test_list_empty(self):
        """GET should return empty list when no archive history."""
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["archive_history"], [])

    def test_list_after_archive_restore(self):
        """GET should return archive and restore entries."""
        from hc.api.models import ArchiveLog
        ArchiveLog.objects.create(owner=self.check, action="archived", by="alice@example.org")
        ArchiveLog.objects.create(owner=self.check, action="restored", by="bob@example.org")
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        history = r.json()["archive_history"]
        self.assertEqual(len(history), 2)
        actions = [h["action"] for h in history]
        self.assertIn("archived", actions)
        self.assertIn("restored", actions)

    def test_archive_history_ordered_newest_first(self):
        """GET archive-history should return entries ordered newest first."""
        from hc.api.models import ArchiveLog
        past = now() - td(hours=1)
        log_old = ArchiveLog.objects.create(owner=self.check, action="archived", by="")
        log_old.at = past
        log_old.save(update_fields=["at"])
        log_new = ArchiveLog.objects.create(owner=self.check, action="restored", by="")
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        history = r.json()["archive_history"]
        self.assertEqual(history[0]["action"], "restored")
        self.assertEqual(history[1]["action"], "archived")

    def test_wrong_project_returns_403(self):
        """GET for check in different project should return 403."""
        other = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other.code}/archive-history/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_returns_404(self):
        """GET for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/archive-history/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_list_doesnt_include_other_checks_logs(self):
        """Archive-history must filter by owner; other checks' logs must not appear."""
        from hc.api.models import ArchiveLog
        other = Check.objects.create(project=self.project, name="Other")
        ArchiveLog.objects.create(owner=other, action="archived", by="")
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["archive_history"], [])

    def test_list_after_archive_restore_has_correct_shape(self):
        """Archive-history entries must have uuid, check, action, at, by."""
        from hc.api.models import ArchiveLog
        ArchiveLog.objects.create(owner=self.check, action="archived", by="alice@example.org")
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        history = r.json()["archive_history"]
        self.assertEqual(len(history), 1)
        entry = history[0]
        for key in ("uuid", "check", "action", "at", "by"):
            self.assertIn(key, entry, msg=f"archive_history entry must have {key}")


class ArchiveRestoreUrlRoutingTestCase(BaseTestCase):
    """Tests for URL routing across API versions."""

    def setUp(self):
        super().setUp()

    def test_v1_archive_endpoint(self):
        """POST archive should work under /api/v1/."""
        check = Check.objects.create(project=self.project, name="Test v1")
        r = self.client.post(
            f"/api/v1/checks/{check.code}/archive/",
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

    def test_v3_archive_endpoint(self):
        """POST archive should work under /api/v3/."""
        check = Check.objects.create(project=self.project, name="Test v3")
        r = self.client.post(
            f"/api/v3/checks/{check.code}/archive/",
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

    def test_v3_restore_endpoint(self):
        """POST restore should work under /api/v3/."""
        check = Check.objects.create(project=self.project, name="Test restore")
        check.archived_at = now()
        check.save()
        r = self.client.post(
            f"/api/v3/checks/{check.code}/restore/",
            json.dumps({"api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

    def test_v3_archive_history_endpoint(self):
        """GET archive-history should work under /api/v3/."""
        check = Check.objects.create(project=self.project, name="Test history")
        r = self.client.get(
            f"/api/v3/checks/{check.code}/archive-history/",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r.status_code, 200)

    def test_archive_history_cors(self):
        """GET archive-history should return CORS headers."""
        check = Check.objects.create(project=self.project, name="Test cors")
        r = self.client.get(
            f"/api/v3/checks/{check.code}/archive-history/",
            HTTP_X_API_KEY="X" * 32,
        )
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")

    def test_archive_post_cors(self):
        """POST archive endpoint should send CORS headers (e.g. for OPTIONS)."""
        check = Check.objects.create(project=self.project, name="Test archive cors")
        r = self.client.options(
            f"/api/v3/checks/{check.code}/archive/",
            HTTP_ORIGIN="https://example.com",
        )
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
