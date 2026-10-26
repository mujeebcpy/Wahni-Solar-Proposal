"""Equipment brand lookup and package validation."""

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

    def test_package_brand_allows_hybrid_equipment_without_microinverter_lookup(self):
        doc = frappe._dict(
            package_title="Compatible hybrid", brand="Deye", system_type="Hybrid",
            component_rules=[], input_definitions=[], inverter_count_formula="1",
        )
        with patch.object(solar_package, "frappe") as fake:
            solar_package.SolarPackage.validate(doc)
        fake.db.exists.assert_not_called()
        fake.throw.assert_not_called()

    def test_existing_package_name_is_retained_when_title_is_added(self):
        doc = frappe._dict(
            name="Existing package name", package_title=None,
            component_rules=[], input_definitions=[], inverter_count_formula=None,
        )
        solar_package.SolarPackage.validate(doc)
        self.assertEqual(doc.package_title, "Existing package name")
        self.assertEqual(doc.name, "Existing package name")
