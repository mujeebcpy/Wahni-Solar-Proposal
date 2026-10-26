"""Demo provenance, repeatability, cleanup boundaries and saved print snapshots."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from jinja2 import Environment

from wahni_solar.wahni_solar_proposal import demo


def item(code, name, group, uom="Nos", brand=""):
    return {"name": code, "item_name": name, "item_group": group, "stock_uom": uom,
            "brand": brand, "description": name}


ITEMS = [
    item("INV-EXISTING", "IQ8P", "Microinverters", brand="Enphase"),
    item("RED-EXISTING", "Red 6 sqmm AC cable", "Cables", "Meter"),
    item("BLUE-EXISTING", "Blue 6 sqmm AC cable", "Cables", "Meter"),
    item("CLAMP-EXISTING", "Cable support clamp", "Hardware"),
    item("SCREW-EXISTING", "Screw", "Hardware"),
    item("PLUG-EXISTING", "Wall plug", "Hardware"),
]


class TestDemoConfiguration(unittest.TestCase):
    def test_discovery_selects_a_microinverter_and_meter_cable(self):
        roles = demo._discover_items(ITEMS + [
            item("CABLE-ROLL", "Red 6 sqmm cable", "Cables", "Roll"),
            item("INV-STRING", "Solar string inverter", "Inverters"),
        ])
        self.assertEqual(roles["inverter"]["name"], "INV-EXISTING")
        self.assertEqual(roles["red_cable"]["name"], "RED-EXISTING")
        self.assertEqual(roles["cable"]["stock_uom"], "Meter")

    def test_actual_earthing_role_outranks_an_unrelated_item_in_earthing_group(self):
        roles = demo._discover_items([
            item("A-DOWN-CONDUCTOR", "Down Conductor - Al/8mm", "Earthing Kit", "Meter"),
            item("Z-EARTHING-ROD", "Earthing Rod - Copper Bonded/4ft", "Earthing Kit"),
        ])
        self.assertEqual(roles["earth"]["name"], "Z-EARTHING-ROD")

    def test_ac_six_sqmm_is_preferred_to_a_dc_or_different_size_cable(self):
        roles = demo._discover_items([
            item("A-DC", "Red DC cable 6 sqmm", "Cables", "Meter"),
            item("B-AC-OTHER", "Red AC cable 4 sqmm", "Cables", "Meter"),
            item("Z-AC", "Red AC cable 6 sqmm", "Cables", "Meter"),
        ])
        self.assertEqual(roles["cable"]["name"], "Z-AC")
        self.assertEqual(roles["red_cable"]["name"], "Z-AC")

    def test_cleared_defaults_do_not_reappear_on_migration(self):
        fake = MagicMock()
        fake.db.get_single_value.return_value = 1
        with patch.object(demo, "frappe", fake):
            result = demo.seed_demo_configuration()
        self.assertFalse(result["created"])
        fake.get_all.assert_not_called()
        fake.get_doc.assert_not_called()

    def test_seed_is_repeatable_and_never_replaces_staff_edits_or_inserts_items(self):
        fake = MagicMock()
        fake.db.get_single_value.return_value = 0
        fake.get_all.return_value = ITEMS
        records = {}

        def get_value(doctype, filters, field):
            if isinstance(filters, dict):
                title = next(iter(filters.values()))
                return title if (doctype, title) in records else None
            return records[(doctype, filters)][field]

        def get_doc(values):
            title = values.get("template_name") or values.get("package_title")
            doc = MagicMock()
            doc.name = title
            doc.insert.side_effect = lambda **kwargs: records.update({(values["doctype"], title): values})
            return doc

        fake.db.get_value.side_effect = get_value
        fake.get_doc.side_effect = get_doc
        with patch.object(demo, "frappe", fake):
            first = demo.seed_demo_configuration()
            template_key = ("Solar Component Template", demo.PREFIX + "Downrun")
            records[template_key]["notes"] = "Staff changed this"
            second = demo.seed_demo_configuration()
        self.assertTrue(first["packages"])
        self.assertFalse(second["created"])
        self.assertEqual(records[template_key]["notes"], "Staff changed this")
        self.assertTrue(all(key[0] in ("Solar Package", "Solar Component Template") for key in records))
        rule_rows = records[template_key]["items"]
        self.assertIn('qty("clamp") * 2', [row["quantity_formula"] for row in rule_rows])
        self.assertIn('0 if self_screws else qty("screw")', [row["quantity_formula"] for row in rule_rows])
        looping = records[("Solar Component Template", demo.PREFIX + "Downrun to DB Looping")]["items"]
        self.assertIn('phase == "Three Phase"', [row["include_when"] for row in looping])
        fake.db.set_value.assert_not_called()

    def test_missing_suitable_items_does_not_create_placeholder_inventory(self):
        fake = MagicMock()
        fake.db.get_single_value.return_value = 0
        fake.get_all.return_value = [item("CABLE", "Cable", "Cables", "Roll")]
        with patch.object(demo, "frappe", fake):
            report = demo.seed_demo_configuration()
        self.assertTrue(report["warnings"])
        fake.get_doc.assert_not_called()

    def test_cleanup_checks_demo_tags_and_preserves_links_and_attachments(self):
        fake = MagicMock()
        fake.LinkExistsError = type("LinkExistsError", (Exception,), {})
        names = {"Solar Proposal": ["FREE", "PROJECT", "ATTACHMENT"],
                 "Solar Package": ["USED-PACKAGE"], "Solar Component Template": ["FREE-TEMPLATE"]}
        fake.get_all.side_effect = lambda doctype, **kwargs: names[doctype]
        fake.db.exists.side_effect = lambda doctype, filters: (
            filters["attached_to_name"] == "ATTACHMENT" if doctype == "File"
            else filters["custom_solar_proposal"] == "PROJECT"
        )

        def delete(doctype, name, **kwargs):
            if name == "USED-PACKAGE":
                raise fake.LinkExistsError()

        fake.delete_doc.side_effect = delete
        with patch.object(demo, "frappe", fake):
            report = demo.clear_demo_configuration()
        self.assertEqual({record["name"] for record in report["deleted"]}, {"FREE", "FREE-TEMPLATE"})
        self.assertEqual({record["name"] for record in report["skipped"]}, {"PROJECT", "ATTACHMENT", "USED-PACKAGE"})
        for call in fake.get_all.call_args_list:
            self.assertEqual(call.kwargs["filters"], {"is_demo": 1})
        for call in fake.delete_doc.call_args_list:
            self.assertNotIn("force", call.kwargs)
        fake.db.set_single_value.assert_called_once_with(demo.SETTINGS, "demo_defaults_cleared", 1)
        fake.only_for.assert_called_once_with("System Manager")


class PrintRecord(dict):
    def __getattr__(self, key):
        return self.get(key)


class TestProposalPrintSnapshot(unittest.TestCase):
    def render(self, **changes):
        path = Path(__file__).parent / "print_format" / "solar_proposal" / "solar_proposal.json"
        template = json.loads(path.read_text())["html"]
        db = MagicMock()
        db.get_value.return_value = None
        db.get_all.return_value = []
        utils = SimpleNamespace(formatdate=lambda value: value, fmt_money=lambda value: f"{value or 0:,.2f}")
        record = PrintRecord(name="PRINT-SNAPSHOT", customer_name="Sample customer", proposal_to="Customer",
                             proposal_date="2026-10-23", system_name="Saved system", package_name="PACKAGE",
                             brand="Enphase", connection_type="Three Phase", grid_type="On-Grid",
                             capacity_kw=3, panel_capacity_w=660, suggested_panel_count=5, panel_count=6,
                             actual_capacity_kw=3.96, inverter_count=6, include_structure=1,
                             panel_brand="Adani", project_cost=100000, discount=1000, subsidy=78000,
                             final_amount=21000, down_run_cabling="Armoured Cabling", table_proposal_bom=[
                                 PrintRecord(component_group="Downrun", component_label="Saved cable role",
                                             item_name="Saved actual Item", item_code="REMOVED-ITEM",
                                             description="Saved cable specification", quantity=8, uom="Meter")])
        record.update(changes)
        html = Environment(autoescape=True).from_string(template).render(
            doc=record, frappe=SimpleNamespace(db=db, utils=utils))
        return html, db

    def test_snapshot_prints_actual_staff_panel_count_materials_and_discount(self):
        html, db = self.render()
        for text in ("Number of panels: 6", "Suggested panel count: 5", "3.96 kWp",
                     "Saved cable role", "Saved actual Item", "Saved cable specification", "8 Meter",
                     "Discount", "1,000.00", "21,000.00"):
            self.assertIn(text, html)
        for call in db.get_value.call_args_list:
            self.assertNotIn(call.args[0], ("Item", "Solar Package"))
        self.assertNotIn("480", html)

    def test_legacy_material_rows_render_without_new_snapshot_fields(self):
        html, _ = self.render(system_name=None, panel_capacity_w=None, actual_capacity_kw=None,
                              inverter_count=None, table_proposal_bom=[
                                  PrintRecord(item_code="LEGACY-ITEM", quantity=3, uom="Nos")])
        self.assertIn("LEGACY-ITEM", html)
        self.assertIn("3 Nos", html)

    def test_unknown_legacy_inverter_count_is_not_printed_as_zero(self):
        html, _ = self.render(calculation_version="Legacy", inverter_count=0)
        self.assertNotIn("Number of inverters", html)


if __name__ == "__main__":
    unittest.main()
