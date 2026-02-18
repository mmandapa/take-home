"""Tests for the Ping Labels feature."""
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


class PingLabelModelTestCase(BaseTestCase):
    """Tests for the PingLabel model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_ping_label_model_exists(self):
        from hc.api.models import PingLabel
        self.assertTrue(hasattr(PingLabel, "objects"))

    def test_create_ping_label(self):
        from hc.api.models import PingLabel
        lb = PingLabel.objects.create(owner=self.check, name="deploy")
        self.assertIsNotNone(lb.code)
        self.assertEqual(lb.name, "deploy")

    def test_to_dict(self):
        from hc.api.models import PingLabel
        lb = PingLabel.objects.create(owner=self.check, name="health")
        d = lb.to_dict()
        self.assertIn("uuid", d)
        self.assertEqual(d["name"], "health")

    def test_to_dict_uuid_is_string(self):
        from hc.api.models import PingLabel
        lb = PingLabel.objects.create(owner=self.check, name="deploy")
        d = lb.to_dict()
        self.assertIsInstance(d["uuid"], str)
        uuid.UUID(d["uuid"])

    def test_ordering(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="zebra")
        PingLabel.objects.create(owner=self.check, name="alpha")
        labels = list(PingLabel.objects.filter(owner=self.check))
        self.assertEqual(labels[0].name, "alpha")
        self.assertEqual(labels[1].name, "zebra")

    def test_unique_per_check(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="deploy")
        with self.assertRaises(Exception):
            PingLabel.objects.create(owner=self.check, name="deploy")

    def test_cascade_delete(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="deploy")
        self.check.delete()
        self.assertEqual(PingLabel.objects.count(), 0)


class CreateLabelApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/labels/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/labels/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_create_label(self):
        r = self.post({"name": "deploy"})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertIn("uuid", doc)
        self.assertEqual(doc["name"], "deploy")

    def test_name_required(self):
        r = self.post({})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.json()["error"].lower())

    def test_name_empty(self):
        r = self.post({"name": "   "})
        self.assertEqual(r.status_code, 400)

    def test_name_too_long(self):
        r = self.post({"name": "x" * 101})
        self.assertEqual(r.status_code, 400)
        self.assertIn("long", r.json()["error"].lower())

    def test_duplicate_name(self):
        self.post({"name": "deploy"})
        r = self.post({"name": "deploy"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("already", r.json()["error"].lower())

    def test_wrong_project(self):
        other = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other.code}/labels/"
        r = self.client.post(
            url,
            json.dumps({"name": "deploy", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        url = f"/api/v3/checks/{uuid.uuid4()}/labels/"
        r = self.client.post(
            url,
            json.dumps({"name": "deploy", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_post_wrong_api_key(self):
        r = self.post({"name": "deploy"}, api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_name_exactly_100_chars_succeeds(self):
        r = self.post({"name": "x" * 100})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.json()["name"]), 100)

    def test_name_not_string(self):
        r = self.client.post(
            self.url,
            json.dumps({"name": 123, "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        err = r.json().get("error", "").lower()
        self.assertTrue("name" in err or "string" in err)

    def test_empty_string_name(self):
        r = self.post({"name": ""})
        self.assertEqual(r.status_code, 400)

    def test_create_response_has_uuid_and_name(self):
        r = self.post({"name": "deploy"})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertIn("uuid", doc)
        self.assertIn("name", doc)
        self.assertIsInstance(doc["uuid"], str)
        self.assertIsInstance(doc["name"], str)
        self.assertEqual(doc["name"], "deploy")

    def test_duplicate_name_error_message(self):
        self.post({"name": "deploy"})
        r = self.post({"name": "deploy"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("error", r.json())
        self.assertIn("already", r.json()["error"].lower())


class ListLabelsApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/labels/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/labels/"

    def get(self, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.get(self.url, HTTP_X_API_KEY=api_key)

    def test_list_empty(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["labels"], [])

    def test_list_labels(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="deploy")
        PingLabel.objects.create(owner=self.check, name="health")
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["labels"]), 2)
        names = [lb["name"] for lb in r.json()["labels"]]
        self.assertIn("deploy", names)
        self.assertIn("health", names)

    def test_wrong_api_key(self):
        r = self.get(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_nonexistent_check(self):
        url = f"/api/v3/checks/{uuid.uuid4()}/labels/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_get_wrong_project(self):
        other = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other.code}/labels/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_list_ordering_by_name(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="zebra")
        PingLabel.objects.create(owner=self.check, name="alpha")
        PingLabel.objects.create(owner=self.check, name="middle")
        r = self.get()
        self.assertEqual(r.status_code, 200)
        names = [lb["name"] for lb in r.json()["labels"]]
        self.assertEqual(names, ["alpha", "middle", "zebra"])

    def test_list_only_this_check_labels(self):
        from hc.api.models import PingLabel
        other_check = Check.objects.create(project=self.bobs_project, name="Other")
        PingLabel.objects.create(owner=self.check, name="mine")
        PingLabel.objects.create(owner=other_check, name="theirs")
        r = self.get()
        self.assertEqual(r.status_code, 200)
        labels = r.json()["labels"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["name"], "mine")

    def test_list_empty_response_shape(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("labels", data)
        self.assertEqual(data["labels"], [])


class PingWithLabelTestCase(BaseTestCase):
    """Tests that pings can have a label and it appears in ping list."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_ping_with_label_appears_in_list(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="deploy")
        # Create ping via HTTP with ?label=deploy
        url = f"/ping/{self.check.code}/?label=deploy"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        # List pings
        list_url = f"/api/v3/checks/{self.check.code}/pings/"
        r2 = self.client.get(list_url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r2.status_code, 200)
        pings = r2.json()["pings"]
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0].get("label"), "deploy")

    def test_ping_without_label_has_none(self):
        url = f"/ping/{self.check.code}/"
        self.client.get(url)
        list_url = f"/api/v3/checks/{self.check.code}/pings/"
        r = self.client.get(list_url, HTTP_X_API_KEY="X" * 32)
        pings = r.json()["pings"]
        self.assertEqual(len(pings), 1)
        self.assertIsNone(pings[0].get("label"))

    def test_ping_with_unknown_label_ignored(self):
        url = f"/ping/{self.check.code}/?label=nosuchlabel"
        self.client.get(url)
        list_url = f"/api/v3/checks/{self.check.code}/pings/"
        r = self.client.get(list_url, HTTP_X_API_KEY="X" * 32)
        pings = r.json()["pings"]
        self.assertEqual(len(pings), 1)
        self.assertIsNone(pings[0].get("label"))

    def test_ping_label_in_list_matches_created(self):
        from hc.api.models import PingLabel
        PingLabel.objects.create(owner=self.check, name="production")
        url = f"/ping/{self.check.code}/?label=production"
        self.client.get(url)
        list_url = f"/api/v3/checks/{self.check.code}/pings/"
        r = self.client.get(list_url, HTTP_X_API_KEY="X" * 32)
        pings = r.json()["pings"]
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0]["label"], "production")


class LabelsUrlRoutingTestCase(BaseTestCase):
    """Tests for URL routing (v1/v2/v3)."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_v1_endpoint(self):
        url = f"/api/v1/checks/{self.check.code}/labels/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v2_endpoint(self):
        url = f"/api/v2/checks/{self.check.code}/labels/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v3_endpoint(self):
        url = f"/api/v3/checks/{self.check.code}/labels/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_options_request(self):
        url = f"/api/v3/checks/{self.check.code}/labels/"
        r = self.client.options(url)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")

    def test_options_allow_methods(self):
        url = f"/api/v3/checks/{self.check.code}/labels/"
        r = self.client.options(url)
        self.assertEqual(r.status_code, 204)
        allow_methods = r.get("Access-Control-Allow-Methods", "")
        self.assertIn("GET", allow_methods)
        self.assertIn("POST", allow_methods)
