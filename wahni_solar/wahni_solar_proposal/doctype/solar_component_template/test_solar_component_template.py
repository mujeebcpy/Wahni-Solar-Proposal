"""Validation of reusable material rules without needing an installed site."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from wahni_solar.wahni_solar_proposal.doctype.solar_component_template import solar_component_template


def fail(message, *args, **kwargs):
    raise ValueError(message)


class TestSolarComponentTemplate(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(solar_component_template.frappe, "throw", side_effect=fail)
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self, **values):
        fields = dict(idx=1, rule_key="clamp", include_when="", quantity_formula="route_length * 2",
                      enabled=1, item_code="CLAMP", uom="Nos", description="Saved specification")
        fields.update(values)
        return SimpleNamespace(**fields)

    def template(self, rows):
        return SimpleNamespace(items=rows, validation_condition=None)

    def test_empty_template_and_package_specific_variables_are_allowed(self):
        solar_component_template.SolarComponentTemplate.validate(self.template([]))
        solar_component_template.SolarComponentTemplate.validate(self.template([self.row()]))

    def test_duplicate_rule_keys_and_unrestricted_code_are_rejected(self):
        for rows in ([self.row(), self.row(idx=2)], [self.row(quantity_formula='__import__("os")')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                solar_component_template.SolarComponentTemplate.validate(self.template(rows))

    def test_item_defaults_fill_missing_values_without_overwriting_specifications(self):
        defaults = SimpleNamespace(stock_uom="Nos", description="Item specification")
        row = self.row(uom=None)
        with patch.object(solar_component_template, "frappe") as fake:
            fake.db.get_value.return_value = defaults
            solar_component_template.SolarComponentTemplate.validate(self.template([row]))
        self.assertEqual(row.uom, "Nos")
        self.assertEqual(row.description, "Saved specification")

    def test_missing_enabled_quantity_formula_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Quantity Formula"):
            solar_component_template.SolarComponentTemplate.validate(self.template([self.row(quantity_formula="")]))
