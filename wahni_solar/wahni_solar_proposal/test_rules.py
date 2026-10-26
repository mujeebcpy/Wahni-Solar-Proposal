"""Pure-Python tests: run with python -m unittest <this module>."""

import unittest

from wahni_solar.wahni_solar_proposal.rules import (
	MAX_DEPENDENCY_DEPTH,
	MAX_EXPRESSION_LENGTH,
	RuleError,
	evaluate,
	evaluate_materials,
	validate_expression,
)


def item(key, formula, **kwargs):
	return {
		"rule_key": key,
		"quantity_formula": formula,
		"component_label": key.replace("_", " ").title(),
		"item_code": f"ITEM-{key}",
		"uom": "Nos",
		"description": "A staff-selected item",
		**kwargs,
	}


def mapping(alias, items, **kwargs):
	return {
		"template_alias": alias,
		"template": {"name": f"Template {alias}", "group_name": "Staff-defined group", "items": items},
		**kwargs,
	}


class ExpressionTests(unittest.TestCase):
	def test_quantities_and_actual_panel_count_are_inputs(self):
		self.assertEqual(evaluate("ceil(panel_count / 2)", {"panel_count": 7}), 4)
		self.assertEqual(evaluate("ceil(panel_count / 2)", {"panel_count": 9}), 5)
		self.assertEqual(evaluate("ceil(inverter_count / 7)", {"inverter_count": 8}), 2)

	def test_dependencies_include_all_conditional_branches(self):
		self.assertEqual(
			validate_expression('qty("cable") * 2 if self_screws else qty("other.screw")'),
			{"variables": {"self_screws"}, "quantities": {"cable", "other.screw"}},
		)

	def test_approved_numeric_helpers(self):
		self.assertEqual(evaluate("ceil(1.1) + floor(2.9) + abs(-3)", {}), 7)
		self.assertEqual(evaluate("round(max(1.1, min(4, 2.345)), 2)", {}), 2.35)
		self.assertEqual(evaluate("7 // 2 + 7 % 2", {}), 4)
		self.assertEqual(evaluate("-2 + 5", {}), 3)

	def test_boolean_comparisons_and_lazy_conditions(self):
		context = {"phase": "Three Phase", "distance": 4, "include_battery": 1}
		self.assertTrue(evaluate('phase == "Three Phase" and distance > 3', context))
		self.assertTrue(evaluate("0 < distance <= 4", context))
		self.assertEqual(evaluate("2 if include_battery else 1 / 0", context), 2)
		self.assertFalse(evaluate("False and 1 / 0 > 0", {}))
		self.assertTrue(evaluate("True or 1 / 0 > 0", {}))
		self.assertFalse(evaluate("not include_battery", context))

	def test_literal_qty_resolver(self):
		self.assertEqual(evaluate('qty("cable") * 2', {}, lambda key: {"cable": 25}[key]), 50)
		with self.assertRaisesRegex(RuleError, "resolver"):
			evaluate('qty("cable")', {})
		with self.assertRaisesRegex(RuleError, "not allowed"):
			validate_expression('qty("cable")', allow_qty=False)
		with self.assertRaisesRegex(RuleError, "Unknown quantity"):
			evaluate('qty("typo")', {}, lambda key: {}[key])

	def test_unknown_variables_rejected_in_unselected_branches(self):
		with self.assertRaisesRegex(RuleError, "Unknown variable: typo"):
			evaluate("1 if True else typo", {})

	def test_forbidden_syntax_cannot_reach_python_objects(self):
		payloads = [
			'__import__("os")',
			"panel_count.__class__",
			"panel_count[0]",
			"[x for x in panel_count]",
			"(lambda: 1)()",
			"[1, 2]",
			"{'a': 1}",
			"(x := 1)",
			"f'{panel_count}'",
			"2 ** 100",
			"round(1.5, ndigits=1)",
			"max(*panel_count)",
			'qty(panel_count)',
			'qty("a" + "b")',
			'qty("a.b.c")',
		]
		for payload in payloads:
			with self.subTest(payload=payload), self.assertRaises(RuleError):
				validate_expression(payload)

	def test_numeric_and_resource_limits(self):
		payloads = [
			"9" * 1000,
			"1e309",
			"-1",
			"1 / 0",
			"1000000000000 * 1000000000000",
			"round(2, 100)",
			"+".join(["1"] * 150),
			"-" * 40 + "1",
			"1 " * MAX_EXPRESSION_LENGTH,
		]
		for payload in payloads:
			with self.subTest(payload=payload[:50]), self.assertRaises(RuleError):
				evaluate(payload, {})
		for invalid in [float("inf"), float("nan"), 10**1000, object()]:
			with self.subTest(value=type(invalid)), self.assertRaises(RuleError):
				evaluate("value", {"value": invalid})

	def test_inappropriate_types_and_boolean_results(self):
		for expr in ['"1" + "2"', 'ceil("3")', "True * 2", "2 if 4 else 0"]:
			with self.subTest(expr=expr), self.assertRaises(RuleError):
				evaluate(expr, {})


class MaterialTests(unittest.TestCase):
	def test_dependency_order_does_not_depend_on_visual_row_order(self):
		materials = [
			item("plug", '0 if self_screws else qty("screw")'),
			item("screw", 'qty("clamp") * 2'),
			item("clamp", 'qty("cable") * 2'),
			item("cable", "route_length", uom="Meter"),
		]
		rows = evaluate_materials([mapping("run", materials)], {"route_length": 25, "self_screws": 0})
		self.assertEqual([row["quantity"] for row in rows], [100, 100, 50, 25])
		self.assertEqual(rows[0]["source_template"], "Template run")
		self.assertEqual(rows[0]["component_group"], "Staff-defined group")
		self.assertIn("qty('screw')=100", rows[0]["calculation_note"])
		self.assertIn("route_length=25", rows[-1]["calculation_note"])

	def test_cross_template_references_and_reused_template_instances(self):
		source = mapping("source", [item("cable", "5")])
		consumer = mapping("consumer", [item("clamp", 'qty("source.cable") * 2')])
		other = {**source, "template_alias": "other"}
		rows = evaluate_materials([consumer, source, other], {})
		self.assertEqual([row["quantity"] for row in rows], [10, 5, 5])
		self.assertEqual([row["template_alias"] for row in rows], ["consumer", "source", "other"])

	def test_excluded_optional_templates_and_rows_are_known_zeroes(self):
		battery = mapping("battery", [item("pack", "2")], include_when="include_battery")
		common = mapping("common", [item("label", 'qty("battery.pack") + qty("hidden")'),
			item("hidden", "5", include_when="False")])
		self.assertEqual(evaluate_materials([battery, common], {"include_battery": 0}), [])
		rows = evaluate_materials([battery, common], {"include_battery": 1})
		self.assertEqual([row["quantity"] for row in rows], [2, 2])

	def test_conditions_can_depend_on_other_template_quantities(self):
		source = mapping("source", [item("cable", "route_length")])
		consumer = mapping("consumer", [item("clamp", 'qty("source.cable") * 2')],
			include_when='qty("source.cable") > 0')
		rows = evaluate_materials([consumer, source], {"route_length": 5})
		self.assertEqual([row["quantity"] for row in rows], [10, 5])
		self.assertEqual(evaluate_materials([consumer, source], {"route_length": 0}), [])

	def test_disabled_flags_and_empty_templates(self):
		rows = [item("disabled", "", enabled=0), item("material", "2")]
		self.assertEqual(evaluate_materials([mapping("off", rows, enabled="0")], {}), [])
		self.assertEqual(evaluate_materials([mapping("empty", [])], {}), [])
		config = mapping("retired", [item("material", "2")])
		config["template"]["disabled"] = 1
		self.assertEqual(evaluate_materials([config], {}), [])

	def test_preview_keeps_excluded_disabled_and_zero_rows_with_diagnostics(self):
		config = mapping("run", [
			item("included", "2"), item("zero", "0"),
			item("excluded", "5", include_when='phase == "Three Phase"'),
			item("disabled", "", enabled=0),
		])
		context = {"phase": "Single Phase"}
		self.assertEqual(len(evaluate_materials([config], context)), 1)
		rows = evaluate_materials([config], context, include_excluded=True)
		self.assertEqual([row["quantity"] for row in rows], [2, 0, 0, 0])
		self.assertEqual([row["included"] for row in rows], [True, True, False, False])
		self.assertIn("is false", rows[2]["calculation_note"])
		self.assertIn("disabled", rows[3]["calculation_note"])
		config["include_when"] = "False"
		rows = evaluate_materials([config], context, include_excluded=True)
		self.assertTrue(all(not row["included"] for row in rows))
		self.assertTrue(all(row["quantity"] == 0 for row in rows))

	def test_effective_overrides_propagate_downstream(self):
		config = mapping("run", [item("clamp", 'qty("cable") * 2'), item("cable", "25")])
		rows = evaluate_materials([config], {}, {"run.cable": {"quantity": 30, "reason": "Site route"}})
		self.assertEqual([row["quantity"] for row in rows], [60, 30])
		self.assertEqual(rows[1]["generated_quantity"], 25)
		self.assertTrue(rows[1]["has_quantity_override"])
		self.assertEqual(rows[1]["override_reason"], "Site route")
		self.assertIn("site override = 30", rows[1]["calculation_note"])

	def test_zero_override_is_retained_but_cannot_enable_excluded_battery(self):
		config = mapping("run", [item("material", "5")])
		rows = evaluate_materials([config], {}, {"run.material": {"quantity": 0, "reason": "Not needed"}})
		self.assertEqual(rows[0]["quantity"], 0)
		self.assertTrue(rows[0]["has_quantity_override"])
		config["include_when"] = "False"
		self.assertEqual(evaluate_materials([config], {}, {"run.material": {"quantity": 3, "reason": "Old"}}), [])

	def test_overrides_require_known_keys_valid_quantities_and_reasons(self):
		config = mapping("run", [item("material", "5")])
		invalid = [
			{"other.material": {"quantity": 1, "reason": "Unknown"}},
			{"run.material": {"quantity": -1, "reason": "Invalid"}},
			{"run.material": {"quantity": 1}},
			{"run.material": {"quantity": 1, "reason": " "}},
		]
		for override in invalid:
			with self.subTest(override=override), self.assertRaises(RuleError):
				evaluate_materials([config], {}, override)

	def test_unknown_quantity_references_rejected_even_when_disabled(self):
		for condition in ["True", "False"]:
			config = mapping("run", [item("material", 'qty("typo")', include_when=condition)], enabled=0)
			with self.subTest(condition=condition), self.assertRaisesRegex(RuleError, "Unknown quantity"):
				evaluate_materials([config], {})

	def test_cycles_in_quantities_and_conditions_are_rejected(self):
		configs = [
			[mapping("run", [item("a", 'qty("b")'), item("b", 'qty("a")')])],
			[mapping("run", [item("a", "2", include_when='qty("a") > 0')])],
			[mapping("run", [item("a", "2")], include_when='qty("a") > 0')],
			[mapping("a", [item("x", 'qty("b.y")')]), mapping("b", [item("y", 'qty("a.x")')])],
		]
		for config in configs:
			with self.subTest(config=config), self.assertRaisesRegex(RuleError, "cycle"):
				evaluate_materials(config, {})

	def test_validation_condition_applies_to_active_empty_templates(self):
		config = mapping("range", [])
		config["template"].update(validation_condition="panel_count <= 18", validation_message="Up to 18 panels")
		with self.assertRaisesRegex(RuleError, "Up to 18 panels"):
			evaluate_materials([config], {"panel_count": 19})
		self.assertEqual(evaluate_materials([config], {"panel_count": 18}), [])
		config["include_when"] = "False"
		self.assertEqual(evaluate_materials([config], {"panel_count": 19}), [])

	def test_duplicate_or_unsafe_keys_are_rejected(self):
		configs = [
			[mapping("same", []), mapping("same", [])],
			[mapping("run", [item("same", "1"), item("same", "2")])],
			[mapping("not.valid", [])],
			[mapping("run", [item("for", "2")])],
		]
		for config in configs:
			with self.subTest(config=config), self.assertRaises(RuleError):
				evaluate_materials(config, {})

	def test_dependency_depth_budget_in_both_visual_orders(self):
		items = [item("row0", "1")]
		items.extend(item(f"row{index}", f'qty("row{index - 1}")') for index in range(1, MAX_DEPENDENCY_DEPTH + 2))
		for ordered in [items, list(reversed(items))]:
			with self.subTest(first=ordered[0]["rule_key"]), self.assertRaisesRegex(RuleError, "too deep"):
				evaluate_materials([mapping("run", ordered)], {})

	def test_invalid_quantity_and_condition_do_not_generate_partial_results(self):
		for bad in [item("bad", "-1"), item("bad", "True"), item("bad", ""),
			item("bad", "2", include_when="4")]:
			with self.subTest(bad=bad), self.assertRaises(RuleError):
				evaluate_materials([mapping("run", [item("good", "1"), bad])], {})

	def test_input_data_is_not_mutated(self):
		config = mapping("run", [item("material", "length")])
		context = {"length": 5}
		rows = evaluate_materials([config], context)
		rows[0]["quantity"] = 99
		self.assertEqual(config["template"]["items"][0]["quantity_formula"], "length")
		self.assertEqual(context, {"length": 5})
		self.assertEqual(evaluate_materials([config], context)[0]["quantity"], 5)


if __name__ == "__main__":
	unittest.main()
