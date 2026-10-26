# Copyright (c) 2026, mujeebcpy and Contributors
# See license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from wahni_solar.wahni_solar_proposal.doctype.solar_package import solar_package


def fail(message, *args, **kwargs):
    raise ValueError(message)


class TestSolarPackage(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(solar_package.frappe, "throw", side_effect=fail)
        patcher.start()
        self.addCleanup(patcher.stop)

    def package(self, **values):
        fields = dict(
            name="Saved package", package_title="Configurable package", component_rules=[],
            input_definitions=[], inverter_count_formula="ceil(panel_count / 2)",
        )
        fields.update(values)
        return SimpleNamespace(**fields)

    def input(self, **values):
        fields = dict(idx=1, variable_key="route_length", input_type="Float", default_value="25",
                      select_options=None, show_when=None)
        fields.update(values)
        return SimpleNamespace(**fields)

    def test_empty_component_lists_and_new_package_input_names_are_allowed(self):
        doc = self.package()
        doc.input_definitions = [self.input(show_when="include_battery")]
        doc.inverter_count_formula = "ceil(panel_count / route_length)"
        solar_package.SolarPackage.validate(doc)

    def test_duplicate_mapping_aliases_and_reserved_input_names_are_rejected(self):
        doc = self.package()
        doc.component_rules = [SimpleNamespace(idx=i, template_alias="downrun", include_when="") for i in (1, 2)]
        with self.assertRaisesRegex(ValueError, "already used"):
            solar_package.SolarPackage.validate(doc)
        doc.component_rules = []
        for name in ("phase", "panel_count", "qty"):
            doc.input_definitions = [self.input(variable_key=name)]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "reserved"):
                solar_package.SolarPackage.validate(doc)

    def test_default_values_are_typed_literals(self):
        for input_type, value in (("Int", "1.5"), ("Float", "nan"), ("Check", "2"), ("Float", "25 * 2"), ("Int", "-1"), ("Float", "-1.2")):
            with self.subTest(input_type=input_type, value=value), self.assertRaisesRegex(ValueError, "valid"):
                solar_package.validate_input_definition(self.input(input_type=input_type, default_value=value))
        solar_package.validate_input_definition(self.input(input_type="Check", default_value="0"))
        solar_package.validate_input_definition(self.input(input_type="Int", default_value="8"))

    def test_select_choices_are_unique_and_contain_the_default(self):
        for choices, default in (("", ""), ("A\nA", "A"), ("A\nB", "C")):
            with self.subTest(choices=choices), self.assertRaises(ValueError):
                solar_package.validate_input_definition(self.input(input_type="Select", select_options=choices, default_value=default))
        solar_package.validate_input_definition(self.input(input_type="Select", select_options="A\nB", default_value="B"))

    def test_inverter_formula_cannot_depend_on_component_quantities_or_itself(self):
        for expression in ('qty("inverter")', "inverter_count + 1"):
            doc = self.package()
            doc.inverter_count_formula = expression
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, "Inverter Count"):
                solar_package.SolarPackage.validate(doc)
