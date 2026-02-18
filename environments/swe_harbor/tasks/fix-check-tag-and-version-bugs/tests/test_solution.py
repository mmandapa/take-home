"""Tests for correct tag filtering and API version behavior (fix-check-tag-and-version-bugs)."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Check
from hc.test import BaseTestCase


class TagFilteringTestCase(BaseTestCase):
    """GET /api/v*/checks/ with tag parameter: space-separated tags, AND semantics, no substring matches."""

    def setUp(self):
        super().setUp()
        self.c1 = Check.objects.create(project=self.project, name="One", tags="foo bar")
        self.c2 = Check.objects.create(project=self.project, name="Two", tags="foo baz")
        self.c3 = Check.objects.create(project=self.project, name="Three", tags="bar baz")
        self.c4 = Check.objects.create(project=self.project, name="Four", tags="startup deploy")

    def get(self, path="/api/v3/checks/", **params):
        from urllib.parse import urlencode
        qs = urlencode(params, doseq=True) if params else ""
        url = path + ("?" + qs if qs else "")
        return self.client.get(url, HTTP_X_API_KEY="X" * 32)

    def test_no_tag_returns_all_checks(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 4)

    def test_single_tag_returns_only_checks_with_that_tag(self):
        r = self.get(tag="foo")
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 2)
        names = {c["name"] for c in checks}
        self.assertEqual(names, {"One", "Two"})

    def test_multiple_tags_and_semantics(self):
        r = self.get(tag=["foo", "bar"])
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["name"], "One")

    def test_tag_no_substring_match(self):
        """Requesting tag 'up' must not match check with tags 'startup deploy'."""
        r = self.get(tag="up")
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 0)

    def test_tag_exact_token_match(self):
        r = self.get(tag="startup")
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["name"], "Four")

    def test_nonexistent_tag_returns_empty(self):
        r = self.get(tag="nonexistent")
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 0)

    def test_tag_filter_scoped_to_project(self):
        other = Check.objects.create(project=self.bobs_project, name="Other", tags="foo")
        r = self.get(tag="foo")
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        names = {c["name"] for c in checks}
        self.assertNotIn("Other", names)
        self.assertEqual(len(checks), 2)

    def test_three_tags_only_one_check_has_all(self):
        """Requesting foo+bar+baz returns only checks that have all three."""
        r = self.get(tag=["foo", "bar", "baz"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["checks"]), 0)

    def test_two_tags_returns_only_matching_check(self):
        r = self.get(tag=["bar", "baz"])
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["name"], "Three")

    def test_response_has_checks_key(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertIn("checks", r.json())
        self.assertIsInstance(r.json()["checks"], list)

    def test_each_check_has_name_and_tags(self):
        r = self.get(tag="foo")
        self.assertEqual(r.status_code, 200)
        for c in r.json()["checks"]:
            self.assertIn("name", c)
            self.assertIn("tags", c)

    def test_tag_filter_on_v1_path(self):
        r = self.get(path="/api/v1/checks/", tag="foo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["checks"]), 2)

    def test_tag_filter_on_v2_path(self):
        r = self.get(path="/api/v2/checks/", tag="bar")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["checks"]), 2)

    def test_duplicate_tag_param_and_semantics(self):
        """tag=foo&tag=foo should still mean AND with one tag 'foo'."""
        r = self.get(tag=["foo", "foo"])
        self.assertEqual(r.status_code, 200)
        names = {c["name"] for c in r.json()["checks"]}
        self.assertEqual(names, {"One", "Two"})


class ApiVersionTestCase(BaseTestCase):
    """GET /api/v1/checks/, v2, v3 return response shape for that version (e.g. update_url uses correct path)."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Vtest", tags="t")

    def get(self, v=3):
        return self.client.get(f"/api/v{v}/checks/", HTTP_X_API_KEY="X" * 32)

    def test_v3_list_returns_v3_update_url(self):
        r = self.get(v=3)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertGreater(len(checks), 0)
        self.assertIn("update_url", checks[0])
        self.assertIn("/api/v3/", checks[0]["update_url"])

    def test_v2_list_returns_v2_update_url(self):
        r = self.get(v=2)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertGreater(len(checks), 0)
        self.assertIn("update_url", checks[0])
        self.assertIn("/api/v2/", checks[0]["update_url"])

    def test_v1_list_returns_v1_update_url(self):
        r = self.get(v=1)
        self.assertEqual(r.status_code, 200)
        checks = r.json()["checks"]
        self.assertGreater(len(checks), 0)
        self.assertIn("update_url", checks[0])
        self.assertIn("/api/v1/", checks[0]["update_url"])

    def test_v3_all_checks_have_v3_update_url(self):
        r = self.get(v=3)
        self.assertEqual(r.status_code, 200)
        for c in r.json()["checks"]:
            self.assertIn("/api/v3/", c["update_url"])

    def test_v2_all_checks_have_v2_update_url(self):
        r = self.get(v=2)
        self.assertEqual(r.status_code, 200)
        for c in r.json()["checks"]:
            self.assertIn("/api/v2/", c["update_url"])

    def test_v3_response_includes_uuid(self):
        r = self.get(v=3)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()["checks"]), 0)
        self.assertIn("uuid", r.json()["checks"][0])

    def test_v1_list_returns_200(self):
        r = self.client.get("/api/v1/checks/", HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)


class ListChecksAuthTestCase(BaseTestCase):
    """401 for bad or missing API key."""

    def test_missing_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/")
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_short_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="short")
        self.assertEqual(r.status_code, 401)

    def test_empty_api_key_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="")
        self.assertEqual(r.status_code, 401)

    def test_api_key_wrong_length_returns_401(self):
        r = self.client.get("/api/v3/checks/", HTTP_X_API_KEY="X" * 31)
        self.assertEqual(r.status_code, 401)


class TagsListModelTestCase(BaseTestCase):
    """tags_list() and matches_tag_set() behave correctly (space-separated)."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="M", tags="a b c")

    def test_tags_list_splits_by_space(self):
        self.assertEqual(self.check.tags_list(), ["a", "b", "c"])

    def test_matches_tag_set_all_present(self):
        self.assertTrue(self.check.matches_tag_set({"a", "b"}))

    def test_matches_tag_set_missing_returns_false(self):
        self.assertFalse(self.check.matches_tag_set({"a", "x"}))

    def test_matches_tag_set_substring_not_match(self):
        check2 = Check.objects.create(project=self.project, name="N", tags="startup")
        self.assertFalse(check2.matches_tag_set({"up"}))

    def test_tags_list_empty_string_returns_empty_list(self):
        c = Check.objects.create(project=self.project, name="Empty", tags="")
        self.assertEqual(c.tags_list(), [])

    def test_tags_list_single_tag(self):
        c = Check.objects.create(project=self.project, name="Single", tags="only")
        self.assertEqual(c.tags_list(), ["only"])

    def test_matches_tag_set_empty_set_returns_true(self):
        """No tags requested: check matches (used when tag filter not applied)."""
        self.assertTrue(self.check.matches_tag_set(set()))

    def test_matches_tag_set_single_tag_present(self):
        self.assertTrue(self.check.matches_tag_set({"b"}))

    def test_tags_list_multiple_spaces_between_tags(self):
        c = Check.objects.create(project=self.project, name="Spaces", tags="a  b   c")
        self.assertEqual(c.tags_list(), ["a", "b", "c"])
