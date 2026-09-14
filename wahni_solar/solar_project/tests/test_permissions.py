"""Report access and deletion behavior."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.solar_project import permissions
from wahni_solar.solar_project.doctype.project_report import project_report as controller


class TestReportDeletion(unittest.TestCase):
    def setUp(self):
        self.report = SimpleNamespace(name="R", project="P", status="Completed")

    def test_only_manager_roles_have_default_delete_permission(self):
        schema = json.loads((Path(controller.__file__).with_suffix(".json")).read_text())
        self.assertEqual({row["role"] for row in schema["permissions"] if row.get("delete")},
                         {"System Manager", "Projects Manager"})

    def test_manager_roles_can_delete_finished_reports(self):
        for role in ("System Manager", "Projects Manager"):
            for status in ("Completed", "Completed with omissions", "Failed"):
                self.report.status = status
                with patch.object(permissions.frappe, "get_roles", return_value=[role]), \
                        patch.object(permissions.frappe, "has_permission", return_value=True) as access:
                    self.assertTrue(permissions.has_report_permission(self.report, "delete", user="manager"))
                access.assert_called_once_with("Project", "read", "P", user="manager")

    def test_administrator_can_delete_finished_reports(self):
        self.assertTrue(permissions.has_report_permission(self.report, "delete", user="Administrator"))

    def test_other_roles_and_inaccessible_projects_are_denied(self):
        for role in ("Sales Manager", "Projects User", "Sales User"):
            with patch.object(permissions.frappe, "get_roles", return_value=[role]):
                self.assertFalse(permissions.has_report_permission(self.report, "delete", user="user"))
        with patch.object(permissions.frappe, "get_roles", return_value=["Projects Manager"]), \
                patch.object(permissions.frappe, "has_permission", return_value=False):
            self.assertFalse(permissions.has_report_permission(self.report, "delete", user="user"))

    def test_active_reports_are_blocked_even_when_permissions_are_bypassed(self):
        for status in ("Queued", "Running"):
            self.report.status = status
            self.assertFalse(permissions.has_report_permission(self.report, "delete", user="Administrator"))
            fake = MagicMock()
            fake.throw.side_effect = frappe.ValidationError("generation active")
            with patch.object(controller, "frappe", fake):
                with self.assertRaises(frappe.ValidationError):
                    controller.ProjectReport.on_trash(self.report)
            fake.db.set_value.assert_not_called()

    def test_deleting_latest_report_restores_previous_report_and_status(self):
        fake = MagicMock()
        fake.db.get_value.return_value = "R"
        fake.get_all.return_value = [{"name": "PREVIOUS", "status": "Failed"}]
        with patch.object(controller, "frappe", fake):
            controller.ProjectReport.on_trash(self.report)
        fake.db.get_value.assert_called_once_with(
            "Project", "P", "custom_latest_project_report", for_update=True, wait=False
        )
        self.assertEqual(fake.get_all.call_args.kwargs["filters"], {"project": "P", "name": ["!=", "R"]})
        fake.db.set_value.assert_called_once_with(
            "Project", "P", {"custom_latest_project_report": "PREVIOUS", "custom_project_report_status": "Failed"},
            update_modified=False,
        )
        fake.db.commit.assert_not_called()

    def test_deleting_only_report_clears_latest_link(self):
        fake = MagicMock()
        fake.db.get_value.return_value = "R"
        fake.get_all.return_value = []
        with patch.object(controller, "frappe", fake):
            controller.ProjectReport.on_trash(self.report)
        fake.db.set_value.assert_called_once_with(
            "Project", "P", {"custom_latest_project_report": None, "custom_project_report_status": None},
            update_modified=False,
        )

    def test_deleting_older_report_does_not_change_latest_link(self):
        fake = MagicMock()
        fake.db.get_value.return_value = "NEWER"
        with patch.object(controller, "frappe", fake):
            controller.ProjectReport.on_trash(self.report)
        fake.get_all.assert_not_called()
        fake.db.set_value.assert_not_called()

