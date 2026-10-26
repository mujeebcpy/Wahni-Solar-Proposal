"""Configuration calculations with isolated Frappe stubs and no database writes."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from wahni_solar.wahni_solar_proposal.rules import RuleError


def load_without_frappe():
	"""Do not replace the real module when these tests run inside a bench."""
	frappe = types.ModuleType("frappe")
	frappe.db = SimpleNamespace(get_value=Mock())
	frappe.get_cached_doc = Mock()
	frappe.get_cached_value = Mock()
	frappe.get_doc = Mock()
	frappe.get_meta = Mock()
	frappe.has_permission = Mock(return_value=True)
	frappe.defaults = SimpleNamespace(get_user_default=Mock())
	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda value: int(value or 0)
	utils.flt = lambda value, precision=None: (
		round(float(value or 0), precision) if precision is not None else float(value or 0)
	)
	utils.now_datetime = lambda: "2026-10-23 12:00:00"
	spec = importlib.util.spec_from_file_location("_solar_configuration_under_test", Path(__file__).with_name("configuration.py"))
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
		spec.loader.exec_module(module)
	return module


configuration = load_without_frappe()


def snapshot(**overrides):
	return {
		"version": configuration.VERSION,
		"package_name": "Staff Package",
		"system_name": "Staff System",
		"brand": "",
		"system_type": "Micro",
		"grid_type": "On-Grid",
		"allow_battery": False,
		"inverter_count_formula": "ceil(panel_count / 2)",
		"input_definitions": [],
		"mappings": [],
		"cost_panel_capacity_w": 600,
		"subsidy_rules": [],
		**overrides,
	}


def values(**overrides):
	return {
		"package_name": "Staff Package", "capacity_kw": 3, "panel_capacity_w": 660,
		"connection_type": "Single Phase", "down_run_cabling": "Conduit Cabling", **overrides,
	}


def definition(key="length", kind="Float", default="8", **overrides):
	return {
		"variable_key": key, "label": key.title(), "input_type": kind,
		"default_value": default, **overrides,
	}


class SystemContextTests(unittest.TestCase):
	def test_suggested_count_and_staff_override_drive_inverter_count(self):
		context, _ = configuration.system_context(snapshot(), values())
		self.assertEqual(context["suggested_panel_count"], 5)
		self.assertEqual(context["panel_count"], 5)
		self.assertEqual(context["inverter_count"], 3)
		self.assertEqual(context["actual_capacity_kw"], 3.3)
		context, _ = configuration.system_context(snapshot(), values(panel_count=7))
		self.assertEqual(context["suggested_panel_count"], 5)
		self.assertEqual(context["panel_count"], 7)
		self.assertEqual(context["inverter_count"], 4)
		self.assertEqual(context["actual_capacity_kw"], 4.62)

	def test_lower_staff_count_remains_a_valid_selected_count(self):
		context, _ = configuration.system_context(snapshot(), values(panel_count=4))
		self.assertEqual(context["panel_count"], 4)
		self.assertEqual(context["actual_capacity_kw"], 2.64)

	def test_invalid_numeric_counts_and_core_inputs_are_rejected(self):
		for changes in [
			{"panel_count": 7.5}, {"panel_count": -1}, {"capacity_kw": 0},
			{"panel_capacity_w": 0}, {"panel_capacity_w": 660.5}, {"capacity_kw": float("nan")},
		]:
			with self.subTest(changes=changes), self.assertRaises(RuleError):
				configuration.system_context(snapshot(), values(**changes))
		for formula in ["1.5", "-1", "True"]:
			with self.subTest(formula=formula), self.assertRaises(RuleError):
				configuration.system_context(snapshot(inverter_count_formula=formula), values())

	def test_staff_defined_inputs_are_typed_and_zero_is_a_valid_required_value(self):
		definitions = [
			definition("length", default="0", required=1),
			definition("self_screws", "Check", "0", required=1),
			definition("choice", "Select", "A", select_options="A\nB", required=1),
		]
		context, rows = configuration.system_context(snapshot(input_definitions=definitions), values())
		self.assertEqual(context["length"], 0.0)
		self.assertIs(context["self_screws"], False)
		self.assertEqual(context["choice"], "A")
		self.assertEqual([row["value"] for row in rows], ["0.0", "0", "A"])
		self.assertEqual(rows[2]["select_options"], "A\nB")

	def test_supplied_input_replaces_default_and_input_type_is_authoritative(self):
		definitions = [definition("length", default="8"), definition("count", "Int", "1")]
		context, _ = configuration.system_context(snapshot(input_definitions=definitions), values(),
			[{"variable_key": "length", "value": "11.5", "input_type": "Data"},
			 {"variable_key": "count", "value": "2"}])
		self.assertEqual(context["length"], 11.5)
		self.assertEqual(context["count"], 2)
		self.assertIsInstance(context["count"], int)

	def test_invalid_select_and_check_values_are_rejected(self):
		for entry, value in [
			(definition("choice", "Select", "A", select_options="A\nB"), "C"),
			(definition("toggle", "Check", "0"), "yes"),
			(definition("number", "Int", "1"), "1.5"),
		]:
			with self.subTest(value=value), self.assertRaises(RuleError):
				configuration.typed_input(entry, value)

	def test_battery_guard_clears_choice_on_incompatible_packages(self):
		for allowed in [False, True]:
			context, _ = configuration.system_context(snapshot(allow_battery=allowed), values(include_battery=1))
			self.assertEqual(context["include_battery"], allowed)
		context, _ = configuration.system_context(snapshot(allow_battery=True), values(include_battery=0))
		self.assertFalse(context["include_battery"])

	def test_hidden_required_input_is_required_only_when_visible(self):
		defs = [definition("battery_count", "Int", "", show_when="include_battery", required=1)]
		config = snapshot(allow_battery=True, input_definitions=defs)
		configuration.system_context(config, values(include_battery=0))
		with self.assertRaisesRegex(RuleError, "Battery_Count"):
			configuration.system_context(config, values(include_battery=1))

	def test_input_visibility_can_reference_calculated_inverter_count(self):
		defs = [definition("length", default="", show_when="inverter_count >= 4", required=1)]
		config = snapshot(input_definitions=defs)
		_, hidden_rows = configuration.system_context(config, values(panel_count=5))
		self.assertEqual(hidden_rows[0]["is_visible"], 0)
		with self.assertRaisesRegex(RuleError, "Length"):
			configuration.system_context(config, values(panel_count=7))
		context, visible_rows = configuration.system_context(config, values(panel_count=7),
			[{"variable_key": "length", "value": "8"}])
		self.assertEqual(context["length"], 8)
		self.assertEqual(visible_rows[0]["is_visible"], 1)

	def test_visibility_requires_a_boolean_or_check_value(self):
		for expression in ['"False"', "5"]:
			config = snapshot(input_definitions=[definition(show_when=expression)])
			with self.subTest(expression=expression), self.assertRaisesRegex(RuleError, "Show When"):
				configuration.system_context(config, values())

	def test_snapshot_parser_returns_an_independent_copy(self):
		live = snapshot(input_definitions=[definition()])
		stored = configuration.parse_snapshot(json.dumps(live))
		live["input_definitions"][0]["default_value"] = "99"
		context, _ = configuration.system_context(stored, values())
		self.assertEqual(context["length"], 8)
		copy_snapshot = configuration.parse_snapshot(stored)
		copy_snapshot["input_definitions"][0]["default_value"] = "100"
		self.assertEqual(stored["input_definitions"][0]["default_value"], "8")


class ChargeAndValuationTests(unittest.TestCase):
	def test_default_charge_quantities_use_actual_panel_count(self):
		doc = values(panel_count=7, cost_breakdown=[
			{"cost_component": "Panel Cost", "rate": 1, "included": 1},
			{"cost_component": "Structure Material", "rate": 100, "included": 1},
			{"cost_component": "Sales Commission", "rate": 10, "included": 1},
		])
		configuration.calculate_charges(doc, snapshot())
		self.assertEqual([row["quantity"] for row in doc["cost_breakdown"]], [7, 4, 3])
		self.assertEqual([row["amount"] for row in doc["cost_breakdown"]], [4200, 400, 30])
		self.assertEqual(doc["other_cost"], 4630)

	def test_auto_charge_quantity_tracks_panel_count_while_manual_quantity_is_preserved(self):
		for previous_quantity, expected in [(3, 4), (9, 9)]:
			row = {"cost_component": "Structure Material", "rate": 100, "included": 1,
				"quantity": previous_quantity}
			previous = values(panel_count=5, cost_breakdown=[copy.deepcopy(row)])
			doc = values(panel_count=7, cost_breakdown=[copy.deepcopy(row)])
			configuration.calculate_charges(doc, snapshot(), previous)
			self.assertEqual(doc["cost_breakdown"][0]["quantity"], expected)

	def test_repeated_new_draft_previews_advance_auto_quantities_but_keep_manual_edits(self):
		doc = values(panel_count=5, cost_breakdown=[
			{"cost_component": "Panel Cost", "rate": 1, "included": 1},
			{"cost_component": "Structure Material", "rate": 100, "included": 1},
		])
		configuration.calculate_charges(doc, snapshot())
		self.assertEqual([row["quantity"] for row in doc["cost_breakdown"]], [5, 3])
		doc["panel_count"] = 7
		configuration.calculate_charges(doc, snapshot())
		self.assertEqual([row["quantity"] for row in doc["cost_breakdown"]], [7, 4])
		self.assertEqual([row["calculated_quantity"] for row in doc["cost_breakdown"]], [7, 4])
		doc["cost_breakdown"][1]["quantity"] = 9
		doc["panel_count"] = 9
		configuration.calculate_charges(doc, snapshot())
		self.assertEqual([row["quantity"] for row in doc["cost_breakdown"]], [9, 9])
		self.assertEqual(doc["cost_breakdown"][1]["calculated_quantity"], 5)

	def test_latest_preview_marker_takes_precedence_over_older_persisted_count(self):
		previous = values(panel_count=5, cost_breakdown=[
			{"cost_component": "Panel Cost", "rate": 1, "quantity": 5, "calculated_quantity": 5, "included": 1},
		])
		doc = {**copy.deepcopy(previous), "panel_count": 7}
		configuration.calculate_charges(doc, snapshot(), previous)
		self.assertEqual(doc["cost_breakdown"][0]["quantity"], 7)
		doc["panel_count"] = 9
		configuration.calculate_charges(doc, snapshot(), previous)
		self.assertEqual(doc["cost_breakdown"][0]["quantity"], 9)
		self.assertEqual(previous["cost_breakdown"][0]["quantity"], 5)

	def test_stock_unit_valuation_converts_to_selected_material_uom(self):
		item = SimpleNamespace(name="Cable", stock_uom="Meter", valuation_rate=150,
			uoms=[SimpleNamespace(uom="Roll", conversion_factor=25)])
		with patch.object(configuration.frappe.db, "get_value", return_value=100):
			valuation = configuration.valuation(item, "Roll", "Warehouse")
			self.assertEqual(valuation["rate"], 2500)
			self.assertEqual(valuation["conversion_factor"], 25)
			self.assertEqual(valuation["valuation_status"], "Valued")
			self.assertEqual(configuration.valuation(item, "Meter", "Warehouse")["rate"], 100)

	def test_missing_conversion_is_unresolved_and_not_assumed_one(self):
		item = SimpleNamespace(name="Cable", stock_uom="Meter", valuation_rate=150, uoms=[])
		with patch.object(configuration.frappe.db, "get_value") as lookup:
			valuation = configuration.valuation(item, "Roll", "Warehouse")
		self.assertEqual(valuation["rate"], 0)
		self.assertEqual(valuation["conversion_factor"], 0)
		self.assertEqual(valuation["valuation_status"], "Missing Conversion")
		lookup.assert_not_called()

	def test_warehouse_without_valuation_uses_item_valuation_but_zero_stays_unresolved(self):
		item = SimpleNamespace(name="Cable", stock_uom="Meter", valuation_rate=150, uoms=[])
		with patch.object(configuration.frappe.db, "get_value", return_value=None):
			self.assertEqual(configuration.valuation(item, "Meter", "Warehouse")["rate"], 150)
			item.valuation_rate = 0
			result = configuration.valuation(item, "Meter", "Warehouse")
		self.assertEqual(result["rate"], 0)
		self.assertEqual(result["valuation_status"], "Missing Valuation")

	def test_disabled_item_keeps_saved_valuation_until_explicit_refresh(self):
		item = SimpleNamespace(name="Cable", stock_uom="Meter", valuation_rate=200, uoms=[],
			item_name="Renamed Item", description="Changed description", disabled=1, has_variants=0,
			check_permission=Mock())
		warehouse = SimpleNamespace(company="Company", is_group=0, disabled=0, check_permission=Mock())
		row = {"template_alias": "run", "rule_key": "cable", "component_label": "Cable",
			"item_code": "Cable", "uom": "Meter", "quantity": 2}
		old = {**row, "item_name": "Saved name", "description": "Saved description", "rate": 100,
			"stock_uom": "Meter", "conversion_factor": 1, "valuation_status": "Valued",
			"valuation_warehouse": "Warehouse"}
		lookup = lambda doctype, name: warehouse if doctype == "Warehouse" else item
		with (
			patch.object(configuration.frappe, "get_doc", side_effect=lookup),
			patch.object(configuration.frappe, "get_cached_value", return_value=0),
			patch.object(configuration.frappe.db, "get_value") as valuation_lookup,
		):
			rows = [copy.deepcopy(row)]
			configuration.price_materials(rows, "Company", "Warehouse", previous_rows=[old])
			self.assertEqual(rows[0]["item_name"], "Saved name")
			self.assertEqual(rows[0]["description"], "Saved description")
			self.assertEqual(rows[0]["rate"], 100)
			self.assertEqual(rows[0]["amount"], 200)
			valuation_lookup.assert_not_called()
			with self.assertRaisesRegex(RuleError, "enabled"):
				configuration.price_materials([copy.deepcopy(row)], "Company", "Warehouse",
					previous_rows=[old], refresh=True)


class SavedConfigurationTests(unittest.TestCase):
	def test_first_generation_seeds_subsidy_but_later_draft_and_saved_zero_is_preserved(self):
		config = snapshot(subsidy_rules=[{"capacity_from": 0, "capacity_to": 3, "subsidy_amount": 78000}])
		settings = SimpleNamespace(costing_company="Company", valuation_warehouse="Warehouse", table_cost_calculation=[])
		doc = values(company="Company", valuation_warehouse="Warehouse", subsidy=0)
		with (
			patch.object(configuration, "load_configuration", return_value=config),
			patch.object(configuration, "price_materials", return_value=[]),
			patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
			patch.object(configuration.frappe, "get_cached_value", return_value="INR"),
		):
			first = configuration.calculate(doc)
			self.assertEqual(first["subsidy"], 78000)
			first["subsidy"] = 0
			later_draft = configuration.calculate(first)
			self.assertEqual(later_draft["subsidy"], 0)
			persisted = configuration.calculate(first, previous=first)
			self.assertEqual(persisted["subsidy"], 0)
			refreshed = configuration.calculate(first, previous=first, refresh_subsidy=True)
			self.assertEqual(refreshed["subsidy"], 78000)

	def test_loaded_snapshot_has_only_logical_json_serializable_child_fields(self):
		metadata = {"creation": datetime(2026, 10, 23), "modified": datetime(2026, 10, 23),
			"owner": "Administrator", "name": "child-name", "doctype": "Child", "parent": "Parent", "idx": 1}
		def child(fields):
			return SimpleNamespace(as_dict=lambda: {**metadata, **fields})
		package = SimpleNamespace(name="Staff Package", package_title="Staff Package", disabled=0,
			brand="", system_type="Micro", grid_type="On-Grid", allow_battery=0,
			inverter_count_formula="panel_count", check_permission=Mock(),
			component_rules=[SimpleNamespace(template_alias="run", component_template="Template", include_when="", enabled=1)],
			input_definitions=[child(definition())])
		template = SimpleNamespace(name="Template", group_name="Custom Group", disabled=0,
			validation_condition="", validation_message="", check_permission=Mock(), items=[child({
				"rule_key": "cable", "component_label": "Cable", "item_code": "Cable Item",
				"uom": "Meter", "quantity_formula": "length", "enabled": 1,
			})])
		settings = SimpleNamespace(panel_max_cacpacity=660, table_subsidy_rule=[child({
			"capacity_from": 0, "capacity_to": 3, "subsidy_amount": Decimal("78000.00"),
		})])
		with (
			patch.object(configuration.frappe, "get_doc", side_effect=[package, template]),
			patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
		):
			loaded = configuration.load_configuration("Staff Package")
		encoded = json.dumps(loaded)
		decoded = json.loads(encoded)
		self.assertEqual(decoded["input_definitions"][0]["default_value"], "8")
		self.assertEqual(decoded["mappings"][0]["template"]["items"][0]["quantity_formula"], "length")
		self.assertEqual(decoded["subsidy_rules"][0]["subsidy_amount"], 78000)
		for rows in [loaded["input_definitions"], loaded["mappings"][0]["template"]["items"], loaded["subsidy_rules"]]:
			for field in metadata:
				self.assertNotIn(field, rows[0])

	def test_saved_defaults_are_used_until_explicit_regeneration(self):
		stored = snapshot(input_definitions=[definition(default="8")])
		live = snapshot(input_definitions=[definition(default="99"), definition("new_length", default="3")])
		previous = values(panel_count=5, configuration_snapshot=stored,
			company="Company", valuation_warehouse="Warehouse", cost_breakdown=[])
		doc = copy.deepcopy(previous)
		doc["input_values"] = [{"variable_key": "length", "value": "11"}]
		settings = SimpleNamespace(costing_company="Company", valuation_warehouse="Warehouse")
		with (
			patch.object(configuration, "load_configuration", return_value=live) as reload_config,
			patch.object(configuration, "price_materials", return_value=[]),
			patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
			patch.object(configuration.frappe, "get_cached_value", return_value="INR"),
		):
			ordinary = configuration.calculate(doc, previous)
			reload_config.assert_not_called()
			self.assertEqual(ordinary["configuration_snapshot"]["input_definitions"][0]["default_value"], "8")
			self.assertEqual(ordinary["input_values"][0]["value"], "11.0")
			self.assertEqual(len(ordinary["input_values"]), 1)
			regenerated = configuration.calculate(doc, previous, regenerate=True)
			reload_config.assert_called_once_with("Staff Package")
			self.assertEqual([row["value"] for row in regenerated["input_values"]], ["11.0", "3.0"])
			self.assertEqual(regenerated["configuration_snapshot"]["input_definitions"][0]["default_value"], "99")
		self.assertEqual(previous["configuration_snapshot"]["input_definitions"][0]["default_value"], "8")

	def test_saved_package_switch_discards_previous_material_overrides(self):
		old = snapshot()
		new = snapshot(package_name="Other Package", mappings=[{
			"template_alias": "other",
			"template": {"name": "New Template", "group_name": "New Group", "items": [{
				"rule_key": "material", "quantity_formula": "2", "item_code": "New Item", "uom": "Nos",
			}]},
		}])
		previous = values(panel_count=5, configuration_snapshot=old, company="Company",
			valuation_warehouse="Warehouse", cost_breakdown=[], table_proposal_bom=[{
				"template_alias": "old", "rule_key": "material", "quantity": 99,
				"has_quantity_override": 1, "override_reason": "Old site choice",
			}])
		doc = {**copy.deepcopy(previous), "package_name": "Other Package"}
		settings = SimpleNamespace(costing_company="Company", valuation_warehouse="Warehouse")
		def price(rows, *_args, **_kwargs):
			for row in rows:
				row.update(amount=row["quantity"], rate=1, valuation_status="Valued")
			return []
		with (
			patch.object(configuration, "load_configuration", return_value=new),
			patch.object(configuration, "price_materials", side_effect=price),
			patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
			patch.object(configuration.frappe, "get_cached_value", return_value="INR"),
		):
			result = configuration.calculate(doc, previous)
		self.assertEqual(result["table_proposal_bom"][0]["template_alias"], "other")
		self.assertEqual(result["table_proposal_bom"][0]["quantity"], 2)
		self.assertFalse(result["table_proposal_bom"][0]["has_quantity_override"])

	def test_warehouse_change_refreshes_rates_and_timestamp(self):
		previous = values(panel_count=5, configuration_snapshot=snapshot(), company="Company",
			valuation_warehouse="Warehouse", pricing_refreshed_on="Old timestamp", cost_breakdown=[])
		settings = SimpleNamespace(costing_company="Company", valuation_warehouse="Warehouse")
		for chosen, should_refresh in [("Warehouse", False), ("Other Warehouse", True)]:
			doc = {**copy.deepcopy(previous), "valuation_warehouse": chosen}
			with (
				patch.object(configuration, "price_materials", return_value=[]) as price,
				patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
				patch.object(configuration.frappe, "get_cached_value", return_value="INR"),
			):
				result = configuration.calculate(doc, previous)
			self.assertEqual(price.call_args.kwargs["refresh"], should_refresh)
			self.assertEqual(result["pricing_refreshed_on"],
				"2026-10-23 12:00:00" if should_refresh else "Old timestamp")

	def test_missing_optional_company_warehouse_field_does_not_query_an_unknown_column(self):
		settings = SimpleNamespace(costing_company="Company", valuation_warehouse=None)
		with (
			patch.object(configuration, "load_configuration", return_value=snapshot()),
			patch.object(configuration.frappe, "get_cached_doc", return_value=settings),
			patch.object(configuration.frappe, "get_meta", return_value=SimpleNamespace(has_field=lambda _: False)),
			patch.object(configuration.frappe, "get_cached_value") as lookup,
		):
			with self.assertRaisesRegex(RuleError, "Set a Valuation Warehouse"):
				configuration.calculate(values(company="Company"))
		lookup.assert_not_called()


if __name__ == "__main__":
	unittest.main()
