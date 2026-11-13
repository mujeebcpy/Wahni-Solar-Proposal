"""Avoid namespace and route collisions without changing the framework or the other app."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from wahni_solar.patches import fix_module_and_workspace_routes as migration
from wahni_solar.patches import add_site_visit_to_dock as dock_migration

APP = Path(__file__).resolve().parents[2]


class TestNavigation(unittest.TestCase):
    def test_visit_has_a_separate_dock_icon_and_sidebar(self):
        dock = json.loads((APP / "dock/wahni_solar/wahni_solar.json").read_text())
        visit = next(row for row in dock["items"] if row["title"] == "Site Visit")
        self.assertEqual((visit["link_type"], visit["link_to"], visit["icon"]), ("Sidebar", "Site Visits", "map-pin"))
        sidebar = json.loads((APP / "site_visit/sidebar/site_visits/site_visits.json").read_text())
        self.assertEqual(sidebar["module"], "Site Visit")
        self.assertEqual(sidebar["name"], "Site Visits")
        self.assertEqual([row["link_to"] for row in sidebar["items"]], ["Site Visits", "Site Visit"])
        proposal = json.loads((APP / "wahni_solar_proposal/sidebar/wahni_solar_proposal/wahni_solar_proposal.json").read_text())
        self.assertNotIn("Site Visits", [row.get("link_to") for row in proposal["items"]])

    def test_workspace_route_does_not_shadow_doctype(self):
        workspace = json.loads((APP / "site_visit/workspace/site_visits/site_visits.json").read_text())
        self.assertEqual(workspace["name"], "Site Visits")
        self.assertEqual(workspace["title"], "Site Visits")
        self.assertEqual(workspace["module"], "Site Visit")
        self.assertEqual(workspace["shortcuts"][0]["link_to"], "Site Visit")

    def test_monitor_namespace_is_unique_and_metadata_is_in_its_module(self):
        modules = (APP / "modules.txt").read_text().splitlines()
        self.assertIn("Wahni Solar Monitor", modules)
        self.assertNotIn("Solar Monitor", modules)
        files = list((APP / "wahni_solar_monitor").rglob("*.json"))
        self.assertEqual(len(files), 7)
        for path in files:
            self.assertEqual(json.loads(path.read_text())["module"], "Wahni Solar Monitor")

    def test_masters_module_and_navigation_are_not_migrated(self):
        with patch.object(migration, "frappe") as fake, patch.object(migration, "rename_doc") as rename:
            fake.db.get_value.side_effect = ["masters_association", None, None]
            migration.execute()
            fake.db.set_value.assert_not_called()
            rename.assert_not_called()

    def test_app_owned_module_moves_without_deleting_records(self):
        with patch.object(migration, "frappe") as fake, patch.object(migration, "rename_doc") as rename:
            fake.db.get_value.side_effect = ["wahni_solar", frappe._dict(module="Site Visit", standard=1)]
            fake.db.exists.return_value = True
            fake.get_meta.return_value.has_field.return_value = True
            migration.execute()
            self.assertEqual(fake.db.set_value.call_count, 7)
            fake.delete_doc.assert_not_called()
            rename.assert_called_once_with(
                "Workspace", "Site Visit", "Site Visits", force=True,
                ignore_permissions=True, show_alert=False, rebuild_search=False,
            )

    def test_already_renamed_workspace_title_is_repaired_idempotently(self):
        with patch.object(migration, "frappe") as fake, patch.object(migration, "rename_doc") as rename:
            fake.db.get_value.side_effect = [None, None, frappe._dict(module="Site Visit", standard=1)]
            migration.execute()
            rename.assert_not_called()
            fake.db.set_value.assert_called_once_with(
                "Workspace", "Site Visits", {"title": "Site Visits", "label": "Site Visits"}, update_modified=False,
            )


class TestVisitDockMigration(unittest.TestCase):
    def test_fresh_site_uses_app_dock_without_creating_a_site_override(self):
        with patch.object(dock_migration, "get_dock", return_value=None) as get_dock, \
                patch.object(dock_migration, "save_site_dock") as save:
            dock_migration.execute()
            get_dock.assert_called_once_with("wahni_solar")
            save.assert_not_called()

    def test_new_entry_preserves_existing_site_order_and_hiding(self):
        existing = [{"link_type": "Sidebar", "link_to": "Wahni Solar Proposal"},
                    {"link_type": "Sidebar", "link_to": "Solar Project", "hidden": 1},
                    {"link_type": "URL", "url": "https://example.com", "title": "Custom"}]
        with patch.object(dock_migration, "get_dock", return_value=object()), \
                patch.object(dock_migration, "dock_rows", return_value=list(existing)), \
                patch.object(dock_migration, "save_site_dock") as save:
            dock_migration.execute()
            save.assert_called_once_with("wahni_solar", [existing[0], {"link_type": "Sidebar", "link_to": "Site Visits"}, *existing[1:]])

    def test_existing_visit_entry_is_not_duplicated_or_unhidden(self):
        with patch.object(dock_migration, "get_dock", return_value=object()), \
                patch.object(dock_migration, "dock_rows", return_value=[{"link_type": "Sidebar", "link_to": "Site Visits", "hidden": 1}]), \
                patch.object(dock_migration, "save_site_dock") as save:
            dock_migration.execute()
            save.assert_not_called()
