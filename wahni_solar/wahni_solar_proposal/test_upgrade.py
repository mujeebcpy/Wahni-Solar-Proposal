"""Retired-schema migration boundaries and private archive guarantees."""

import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from wahni_solar.wahni_solar_proposal import setup, upgrade


class TestLegacyUpgrade(unittest.TestCase):
    def test_archive_is_private_atomic_and_never_overwritten(self):
        fake = MagicMock()
        fake.local.site = "test.local"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.json"
            fake.get_site_path.return_value = str(path)
            with patch.object(upgrade, "frappe", fake):
                first = upgrade._write_archive({"archive_version": 1, "site": "test.local", "packages": ["original"]})
                again = upgrade._write_archive({"archive_version": 1, "site": "test.local", "packages": ["changed"]})
            self.assertEqual(first, again)
            self.assertEqual(json.loads(path.read_text())["packages"], ["original"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_prepare_archives_retired_values_before_writing_unique_titles(self):
        fake = MagicMock()
        fake.local.site = "test.local"
        fake.db.table_exists.return_value = True
        fake.db.has_column.return_value = False
        package = {"name": "OLD", "brand": "Enphase", "connection_type": "Three Phase",
                   "inverter_bom_item": "OLD-BOM-ITEM", "panel_capacity_min": 600}
        rows = {"Solar Package": [package], "Solar Proposal": [{"name": "PROP", "package_name": "OLD"}],
                "Solar Proposal BOM Item": [{"name": "ROW", "item_code": "REAL-ITEM", "quantity": 8}],
                "Item": [{"name": "REAL-ITEM", "item_name": "Cable", "item_group": "Cables"}],
                "Property Setter": []}
        fake.get_all.side_effect = lambda doctype, **kwargs: rows[doctype]
        events = []

        def archive(data):
            events.append("archive")
            self.assertEqual(data["packages"][0]["inverter_bom_item"], "OLD-BOM-ITEM")
            self.assertEqual(data["item_metadata"]["REAL-ITEM"]["item_name"], "Cable")
            self.assertEqual(set(data["retired_package_fields"]), set(upgrade.RETIRED_PACKAGE_FIELDS))
            return data

        fake.db.set_value.side_effect = lambda *args, **kwargs: events.append("title")
        with patch.object(upgrade, "frappe", fake), patch.object(upgrade, "_read_archive", return_value=None), \
                patch.object(upgrade, "_write_archive", side_effect=archive), \
                patch.object(upgrade, "now_datetime", return_value="2026-10-23 12:00:00"), \
                patch.object(upgrade, "archive_path", return_value=Path("archive.json")), \
                patch.object(upgrade, "add_column", side_effect=lambda *args: events.append("column")):
            upgrade.prepare_legacy_configuration()
        self.assertEqual(events, ["archive", "column", "title"])
        fake.db.set_value.assert_called_once_with("Solar Package", "OLD", "package_title", "OLD", update_modified=False)

    def test_post_sync_keeps_linked_history_and_prices_and_drops_only_archived_columns(self):
        fake = MagicMock()
        fake.LinkExistsError = type("LinkExistsError", (Exception,), {})
        fake.db.db_type = "mariadb"
        fake.db.exists.side_effect = lambda doctype, filters: doctype != "File"
        fake.db.has_column.return_value = True
        fake.db.get_value.return_value = None
        fake.get_meta.return_value.get_field.return_value = None
        data = {"packages": [{"name": "LINKED", "brand": "Enphase", "connection_type": "Three Phase"},
                             {"name": "UNUSED", "brand": "Vsole"}],
                "proposals": [{"name": "PROP", "package_name": "LINKED", "panel_count": 6,
                               "project_cost": 50000}],
                "material_rows": [{"name": "ROW", "item_code": "CABLE", "quantity": 25, "rate": 99, "amount": 2475}],
                "item_metadata": {"CABLE": {"item_name": "Saved cable", "description": "Saved spec", "stock_uom": "Meter", "item_group": "Cables"}},
                "property_setters": []}

        def delete(doctype, name, **kwargs):
            if name == "LINKED":
                raise fake.LinkExistsError()

        fake.delete_doc.side_effect = delete
        with patch.object(upgrade, "frappe", fake), patch.object(upgrade, "_read_archive", return_value=data):
            report = upgrade.finish_legacy_configuration()
        self.assertEqual(report, {"deleted_packages": ["UNUSED"], "retained_packages": ["LINKED"]})
        for call in fake.delete_doc.call_args_list:
            self.assertEqual(call.args[0], "Solar Package")
            self.assertNotIn("force", call.kwargs)
        material = next(call.args[2] for call in fake.db.set_value.call_args_list
                        if call.args[0] == "Solar Proposal BOM Item")
        self.assertEqual(material["item_name"], "Saved cable")
        self.assertFalse({"quantity", "rate", "amount"} & material.keys())
        proposal = next(call.args[2] for call in fake.db.set_value.call_args_list if call.args[0] == "Solar Proposal")
        self.assertEqual(proposal["connection_type"], "Three Phase")
        self.assertEqual(proposal["calculation_version"], "Legacy")
        self.assertEqual(proposal["inverter_count"], 6)
        self.assertNotIn("project_cost", proposal)
        sql = fake.db.sql_ddl.call_args.args[0]
        self.assertEqual(sql.count("DROP COLUMN"), 6)
        self.assertTrue(sql.startswith("ALTER TABLE `tabSolar Package` "))
        for field in upgrade.RETIRED_PACKAGE_FIELDS:
            self.assertIn(f"DROP COLUMN `{field}`", sql)

    def test_missing_archive_refuses_column_drops(self):
        fake = MagicMock()
        fake.db.table_exists.return_value = True
        fake.db.has_column.return_value = True
        with patch.object(upgrade, "frappe", fake), patch.object(upgrade, "_read_archive", return_value=None):
            with self.assertRaisesRegex(ValueError, "archive is missing"):
                upgrade.finish_legacy_configuration()
        fake.db.sql_ddl.assert_not_called()


class TestCostingDefaults(unittest.TestCase):
    def test_default_company_without_warehouses_uses_only_existing_stock_company(self):
        fake = MagicMock()
        fake.get_single.return_value = SimpleNamespace(costing_company=None, valuation_warehouse=None)
        fake.defaults.get_global_default.return_value = "No Stock Company"
        fake.db.get_single_value.return_value = None
        fake.get_all.return_value = [{"name": "Stores - WGT", "company": "WGT", "warehouse_name": "Stores"}]
        with patch.object(setup, "frappe", fake):
            self.assertEqual(setup.set_costing_defaults(), [])
        writes = [call.args for call in fake.db.set_single_value.call_args_list]
        self.assertIn((setup.SETTINGS, "costing_company", "WGT"), writes)
        self.assertIn((setup.SETTINGS, "valuation_warehouse", "Stores - WGT"), writes)

    def test_existing_valid_costing_settings_are_preserved(self):
        fake = MagicMock()
        fake.get_single.return_value = SimpleNamespace(costing_company="WGT", valuation_warehouse="Chosen - WGT")
        fake.db.get_single_value.return_value = None
        fake.get_all.return_value = [{"name": "Chosen - WGT", "company": "WGT", "warehouse_name": "Chosen"}]
        with patch.object(setup, "frappe", fake):
            setup.set_costing_defaults()
        fake.db.set_single_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
