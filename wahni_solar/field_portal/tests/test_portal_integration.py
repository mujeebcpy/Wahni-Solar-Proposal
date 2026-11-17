"""Wahni Field shell endpoints on a migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.field_portal.tests.test_portal_integration.run
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from wahni_solar.field_portal import api, renderer
from wahni_solar.field_portal.tests.test_access_integration import TestFieldAccess


class TestFieldPortal(TestFieldAccess):
    def test_session_info_for_eligible_supervisor(self):
        user, employee = self.field_user()
        frappe.set_user(user)
        info = api.get_session_info()
        self.assertTrue(info["allowed"])
        self.assertIsNone(info["reason"])
        self.assertFalse(info["is_office"])
        self.assertEqual(info["employee"]["name"], employee)
        # Only profile fields needed by the app; no salary/HR detail.
        self.assertEqual(set(info["employee"]), {"name", "employee_name", "designation", "department",
                                                 "company", "image", "cell_number"})

    def test_session_info_explains_ineligible_users(self):
        frappe.set_user(self.user("Project Supervisor").name)
        info = api.get_session_info()
        self.assertFalse(info["allowed"])
        self.assertIn("Employee", info["reason"])
        self.assertIsNone(info["employee"])
        frappe.set_user(self.user("Employee").name)
        self.assertFalse(api.get_session_info()["allowed"])
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            api.get_session_info()

    def test_login_options_are_available_to_guests(self):
        frappe.set_user("Guest")
        options = api.get_login_options()
        self.assertIn("password_login", options)
        self.assertIsInstance(options["providers"], list)
        for provider in options["providers"]:
            self.assertNotIn("client_secret", provider)

    def test_whitelisting(self):
        guest_methods = frappe.guest_methods if hasattr(frappe, "guest_methods") else frappe.local.guest_methods
        self.assertIn(api.get_login_options, guest_methods)
        self.assertNotIn(api.get_session_info, guest_methods)
        self.assertNotIn(api.get_csrf_token, guest_methods)

    def test_page_context_is_uncached_and_boot_cannot_break_out_of_script(self):
        from wahni_solar.www import field

        frappe.set_user(self.field_user()[0])
        # No real session object in bench execute; never commit test records.
        csrf = patch.object(frappe.sessions, "get_csrf_token", return_value="token")
        commit = patch.object(frappe.db, "commit")
        csrf.start()
        commit.start()
        self.addCleanup(csrf.stop)
        self.addCleanup(commit.stop)
        with patch.object(field, "get_boot", return_value={"x": "</script><script>alert(1)</script>"}), \
                patch.object(frappe, "request", SimpleNamespace(path="/field/site-visits"), create=True):
            context = field.get_context(frappe._dict())
        self.assertEqual(context.no_cache, 1)
        self.assertTrue(context.csrf_token)
        self.assertNotIn("</script>", context.boot_json)
        self.assertEqual(json.loads(context.boot_json)["x"], "</script><script>alert(1)</script>")
        with patch.object(frappe, "request", SimpleNamespace(path="/field"), create=True), \
                self.assertRaises(frappe.Redirect):
            field.get_context(frappe._dict())
        self.assertEqual(frappe.local.flags.redirect_location, "/field/")

    def test_worker_renderer_only_answers_its_path(self):
        for path, expected in (("/field/sw.js", True), ("/field/", False), ("/field/sw.js.map", False),
                               ("/field/site-visits", False)):
            with patch.object(frappe.local, "request", SimpleNamespace(path=path), create=True):
                self.assertEqual(renderer.FieldWorkerRenderer("field").can_render(), expected, path)
        with patch.object(frappe.local, "request", SimpleNamespace(path="/field/sw.js"), create=True):
            response = renderer.FieldWorkerRenderer("field").render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/field/")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertTrue(response.mimetype.endswith("javascript"))

    def test_route_rules_and_hooks(self):
        rules = frappe.get_hooks("website_route_rules")
        self.assertIn({"from_route": "/field/<path:app_path>", "to_route": "field"}, rules)
        self.assertIn("wahni_solar.field_portal.renderer.FieldWorkerRenderer", frappe.get_hooks("page_renderer"))
        # HRMS keeps its own PWA route.
        self.assertTrue(any(rule.get("to_route") == "hrms" for rule in rules))

    def test_home_summary_counts_only_own_open_work(self):
        user, employee = self.field_user()
        _other_user, other = self.field_user()
        mine = self.site_visit_for(employee)
        self.site_visit_for(other)
        self.pms_for(employee)
        frappe.set_user(user)
        summary = api.get_home_summary()
        self.assertEqual(summary["counts"]["Site Visit"], 1)
        self.assertEqual(summary["counts"]["PMS Visit"], 1)
        self.assertEqual({row["doctype"] for row in summary["recent"]}, {"Site Visit", "PMS Visit"})
        self.assertIn(mine.name, [row["name"] for row in summary["recent"]])


def run():
    names = sorted(name for name in vars(TestFieldPortal) if name.startswith("test_"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(TestFieldPortal(name) for name in names))
    if not result.wasSuccessful():
        raise AssertionError("Field portal integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
