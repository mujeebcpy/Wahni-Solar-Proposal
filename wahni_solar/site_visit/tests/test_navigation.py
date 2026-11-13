"""Avoid namespace and route collisions without changing the framework or the other app."""

import json
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2]


class TestNavigation(unittest.TestCase):
    def test_visit_has_a_separate_dock_icon_and_sidebar(self):
        dock = json.loads((APP / "dock/wahni_solar/wahni_solar.json").read_text())
        visit = next(row for row in dock["items"] if row["title"] == "Site Visit")
        self.assertEqual((visit["link_type"], visit["link_to"], visit["icon"]), ("Sidebar", "Site Visits", "map-pin"))
        sidebar = json.loads((APP / "site_visit/sidebar/site_visits/site_visits.json").read_text())
        self.assertEqual(sidebar["module"], "Site Visit")
        self.assertEqual(sidebar["name"], "Site Visits")
        self.assertEqual([row["link_to"] for row in sidebar["items"]], ["Site Visits", "Site Visit", "PMS Visit"])
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
