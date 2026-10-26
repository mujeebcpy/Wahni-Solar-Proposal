# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import ast
import keyword
import math
import re

import frappe
from frappe.model.document import Document


IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
RESERVED_VARIABLES = {
    "phase", "cabling_type", "capacity_kw", "panel_capacity_w", "panel_count",
    "inverter_count", "include_battery", "brand", "grid_type", "system_type",
    "suggested_panel_count", "actual_capacity_kw", "panel_count_override",
    "ceil", "floor", "min", "max", "abs", "round", "qty", "True", "False", "None",
}
INPUT_TYPES = {"Int", "Float", "Check", "Select", "Data"}


class SolarPackage(Document):
    def validate(self):
        # Existing document names are retained when a title is supplied or changed.
        self.package_title = (self.package_title or self.name or "").strip()
        if not self.package_title:
            frappe.throw("Enter a Package Name.")

        aliases = set()
        for row in self.component_rules or []:
            validate_key(row.template_alias, aliases, f"Component template row {row.idx} alias")
            validate_formula(row.include_when, f"Component template row {row.idx} Include When")

        variables = set()
        for row in self.input_definitions or []:
            validate_key(row.variable_key, variables, f"Input row {row.idx} variable key", reserved=True)
            validate_input_definition(row)

        expression = (self.inverter_count_formula or "panel_count").strip()
        self.inverter_count_formula = expression
        validate_formula(expression, "Inverter Count Formula")
        for node in ast.walk(ast.parse(expression, mode="eval")):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "qty":
                frappe.throw("Inverter Count Formula cannot reference component quantities with qty().")
            if isinstance(node, ast.Name) and node.id == "inverter_count":
                frappe.throw("Inverter Count Formula cannot refer to inverter_count itself.")


def validate_key(value, seen, label, reserved=False):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or keyword.iskeyword(value):
        frappe.throw(f"{label}: use a letter followed by letters, numbers or underscores.")
    if value in seen:
        frappe.throw(f"{label}: '{value}' is already used in this document.")
    if reserved and value in RESERVED_VARIABLES:
        frappe.throw(f"{label}: '{value}' is a reserved variable or helper name.")
    seen.add(value)


def validate_formula(expression, label):
    if not expression:
        return
    from wahni_solar.wahni_solar_proposal.rules import validate_expression

    try:
        validate_expression(expression)
    except (ValueError, SyntaxError) as exc:
        frappe.throw(f"{label}: {exc}")


def validate_input_definition(row):
    label = f"Input row {row.idx} ({row.variable_key})"
    if row.input_type not in INPUT_TYPES:
        frappe.throw(f"{label}: choose Int, Float, Check, Select or Data.")

    choices = [value.strip() for value in (row.select_options or "").splitlines() if value.strip()]
    if row.input_type == "Select":
        if not choices:
            frappe.throw(f"{label}: enter one Select choice per line.")
        if len(choices) != len(set(choices)):
            frappe.throw(f"{label}: Select choices must be unique.")
        row.select_options = "\n".join(choices)

    value = row.default_value
    if value is not None and str(value).strip() != "":
        text = str(value).strip()
        try:
            if row.input_type == "Int":
                if int(text) < 0:
                    raise ValueError
            elif row.input_type == "Float":
                if not math.isfinite(float(text)) or float(text) < 0:
                    raise ValueError
            elif row.input_type == "Check":
                if text not in {"0", "1"}:
                    raise ValueError
            elif row.input_type == "Select" and text not in choices:
                raise ValueError
        except (ValueError, OverflowError):
            frappe.throw(f"{label}: Default Value must be a valid {row.input_type} literal, not a formula. Numeric defaults must be non-negative.")
        if row.input_type in {"Check", "Select"}:
            row.default_value = text

    validate_formula(row.show_when, f"{label} Show When")
