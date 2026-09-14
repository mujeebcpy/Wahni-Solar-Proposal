import unittest
from inspect import unwrap
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.solar_project import equipment
from wahni_solar.wahni_solar_proposal.doctype.solar_package import solar_package


class TestEquipment(unittest.TestCase):
    def test_brand_query_limits_results_to_accessible_microinverter_items(self):
        fake = MagicMock()
        fake.get_list.side_effect = [["Enphase", "Vsole"], [("Enphase",)]]
        with patch.object(equipment, "frappe", fake):
            result = unwrap(equipment.microinverter_brand_query)("Brand", "En", "name", 10, 5, {})
        self.assertEqual(result, [("Enphase",)])
        items, brands = fake.get_list.call_args_list
        self.assertEqual(items.args, ("Item",))
        self.assertEqual(items.kwargs["filters"]["item_group"], "Microinverters")
        self.assertEqual(items.kwargs["filters"]["disabled"], 0)
        self.assertEqual(brands.args, ("Brand",))
        self.assertEqual(brands.kwargs["filters"]["name"], ["in", ["Enphase", "Vsole"]])
        self.assertEqual(brands.kwargs["filters"]["brand"], ["like", "%En%"])
        self.assertEqual(brands.kwargs["start"], 10)
        self.assertEqual(brands.kwargs["page_length"], 5)

    def test_no_eligible_items_does_not_offer_all_brands(self):
        with patch.object(equipment.frappe, "get_list", return_value=[]) as query:
            self.assertEqual(unwrap(equipment.microinverter_brand_query)("Brand", "", "name", 0, 20, {}), [])
        query.assert_called_once()

    def test_brand_lookup_respects_item_read_permissions(self):
        with patch.object(equipment.frappe, "get_list", side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):
                unwrap(equipment.microinverter_brand_query)("Brand", "", "name", 0, 20, {})

    def test_new_or_changed_package_brand_requires_enabled_microinverter(self):
        for previous in (None, frappe._dict(brand="Vsole")):
            for exists in (True, False):
                doc = MagicMock(brand="Enphase")
                doc.get_doc_before_save.return_value = previous
                fake = MagicMock()
                fake.db.exists.return_value = exists
                fake.throw.side_effect = ValueError
                with patch.object(solar_package, "frappe", fake):
                    if exists:
                        solar_package.SolarPackage.validate(doc)
                    else:
                        with self.assertRaises(ValueError):
                            solar_package.SolarPackage.validate(doc)
                fake.db.exists.assert_called_once_with(
                    "Item", {"item_group": "Microinverters", "disabled": 0, "brand": "Enphase"}
                )

    def test_existing_package_brand_remains_editable(self):
        doc = MagicMock(brand="Enphase")
        doc.get_doc_before_save.return_value = frappe._dict(brand="Enphase")
        with patch.object(solar_package, "frappe") as fake:
            solar_package.SolarPackage.validate(doc)
        fake.db.exists.assert_not_called()
        fake.throw.assert_not_called()

    def test_migration_preserves_existing_brand_masters_and_is_repeatable(self):
        fake = MagicMock()
        fake.get_all.return_value = ["Enphase", "Vsole"]
        existing = {"Enphase"}
        fake.db.exists.side_effect = lambda doctype, name: name in existing
        def get_doc(values):
            doc = MagicMock()
            doc.insert.side_effect = lambda **kwargs: existing.add(values["brand"])
            return doc
        fake.get_doc.side_effect = get_doc
        with patch.object(equipment, "frappe", fake):
            equipment.migrate_package_brands()
            equipment.migrate_package_brands()
        self.assertEqual(existing, {"Enphase", "Vsole"})
        fake.get_doc.assert_called_once_with({"doctype": "Brand", "brand": "Vsole"})
