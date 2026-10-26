"""Expand saved configuration data into an authoritative, priced proposal snapshot."""

import copy
import json
import math

import frappe
from frappe.utils import cint, flt, now_datetime

from wahni_solar.wahni_solar_proposal.rules import RuleError, evaluate, evaluate_materials

VERSION = "Templates v1"
CORE_NAMES = {
    "phase", "cabling_type", "capacity_kw", "panel_capacity_w", "panel_count",
    "suggested_panel_count", "inverter_count", "actual_capacity_kw", "include_battery",
    "brand", "system_type", "grid_type",
}
INPUT_TYPES = {"Int", "Float", "Check", "Select", "Data"}
INPUT_DEFINITION_FIELDS = (
    "variable_key", "label", "input_type", "uom", "default_value", "select_options", "show_when", "required",
)
MATERIAL_RULE_FIELDS = (
    "rule_key", "component_label", "item_code", "uom", "include_when", "quantity_formula", "description", "enabled", "notes",
)


def as_dict(value):
    return value.as_dict() if hasattr(value, "as_dict") else dict(value)


def snapshot_fields(value, fields):
    """Keep calculation data; Frappe child metadata contains non-JSON datetimes."""
    values = as_dict(value)
    return {field: values.get(field) for field in fields}


def parse_snapshot(value):
    if isinstance(value, str):
        return json.loads(value) if value else None
    return copy.deepcopy(value) if value else None


def number(value, label, integer=False, positive=False):
    if isinstance(value, bool):
        raise RuleError(f"{label} must be a number, not a Check value.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise RuleError(f"{label} must be a number.") from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise RuleError(f"{label} must be a finite {'positive' if positive else 'non-negative'} number.")
    if integer and not result.is_integer():
        raise RuleError(f"{label} must be a whole number.")
    return int(result) if integer else result


def load_configuration(package_name):
    package = frappe.get_doc("Solar Package", package_name)
    package.check_permission("read")
    if package.disabled:
        raise RuleError("Select an enabled Solar Package.")
    mappings = []
    for link in package.component_rules:
        template = frappe.get_doc("Solar Component Template", link.component_template)
        template.check_permission("read")
        mappings.append({
            "template_alias": link.template_alias,
            "include_when": link.include_when or "",
            "enabled": bool(cint(link.enabled) and not template.disabled),
            "template": {
                "name": template.name, "group_name": template.group_name,
                "validation_condition": template.validation_condition or "",
                "validation_message": template.validation_message or "",
                "items": [snapshot_fields(row, MATERIAL_RULE_FIELDS) for row in template.items],
            },
        })
    if not mappings:
        raise RuleError("Add component templates to this Solar Package first.")
    settings = frappe.get_cached_doc("Wahni Default Settings")
    return {
        "version": VERSION, "package_name": package.name,
        "system_name": package.package_title or package.name,
        "brand": package.brand or "", "system_type": package.system_type or "",
        "grid_type": package.grid_type or "", "allow_battery": bool(package.allow_battery),
        "inverter_count_formula": package.inverter_count_formula,
        "input_definitions": [snapshot_fields(row, INPUT_DEFINITION_FIELDS) for row in package.input_definitions],
        "mappings": mappings,
        "cost_panel_capacity_w": flt(settings.panel_max_cacpacity),
        "subsidy_rules": [
            {key: flt(as_dict(row).get(key)) for key in ("capacity_from", "capacity_to", "subsidy_amount")}
            for row in settings.table_subsidy_rule
        ],
    }


def typed_input(definition, raw):
    kind = definition.get("input_type") or "Data"
    label = definition.get("label") or definition["variable_key"]
    if kind not in INPUT_TYPES:
        raise RuleError(f"{label}: unsupported input type {kind}.")
    if raw is None or raw == "":
        return None
    if kind == "Check":
        if raw in (True, 1, "1", "true", "True"):
            return True
        if raw in (False, 0, "0", "false", "False"):
            return False
        raise RuleError(f"{label} must be Yes or No.")
    if kind in ("Int", "Float"):
        return number(raw, label, integer=kind == "Int")
    value = str(raw)
    if kind == "Select":
        choices = [v.strip() for v in (definition.get("select_options") or "").splitlines() if v.strip()]
        if value not in choices:
            raise RuleError(f"{label}: choose one of {', '.join(choices)}.")
    return value


def input_values(snapshot, supplied, context):
    """Definitions are snapshotted; only values from the client are accepted."""
    supplied = {row.get("variable_key"): row.get("value") for row in supplied or []}
    result = []
    used = set()
    for definition in snapshot.get("input_definitions", []):
        key = definition["variable_key"]
        if key in used or key in CORE_NAMES:
            raise RuleError(f"Duplicate or reserved input key: {key}.")
        used.add(key)
        raw = supplied[key] if key in supplied else definition.get("default_value")
        value = typed_input(definition, raw)
        context[key] = value
        result.append({
            "variable_key": key, "label": definition.get("label") or key,
            "input_type": definition.get("input_type") or "Data", "uom": definition.get("uom"),
            "select_options": definition.get("select_options") or "",
            "show_when": definition.get("show_when") or "", "required": cint(definition.get("required")),
            "value": "" if value is None else str(int(value)) if isinstance(value, bool) else str(value),
        })
    return result


def system_context(snapshot, values, supplied_inputs=None):
    capacity = number(values.get("capacity_kw"), "System Capacity", positive=True)
    watts = number(values.get("panel_capacity_w"), "Panel Capacity", integer=True, positive=True)
    phase = values.get("phase") or values.get("connection_type") or "Single Phase"
    cabling = values.get("cabling_type") or values.get("down_run_cabling") or "Conduit Cabling"
    if phase not in ("Single Phase", "Three Phase"):
        raise RuleError("Select Single Phase or Three Phase.")
    if cabling not in ("Armoured Cabling", "Conduit Cabling"):
        raise RuleError("Select Armoured Cabling or Conduit Cabling.")
    suggested = math.ceil(capacity * 1000 / watts)
    actual = suggested if values.get("panel_count") in (None, "", 0, "0") else number(
        values["panel_count"], "Panel Count", integer=True, positive=True
    )
    context = {
        "capacity_kw": capacity, "panel_capacity_w": watts, "phase": phase, "cabling_type": cabling,
        "suggested_panel_count": suggested, "panel_count": actual,
        "actual_capacity_kw": actual * watts / 1000,
        "include_battery": bool(cint(values.get("include_battery")) and snapshot.get("allow_battery")),
        "brand": snapshot.get("brand") or "", "system_type": snapshot.get("system_type") or "",
        "grid_type": snapshot.get("grid_type") or "",
    }
    rows = input_values(snapshot, supplied_inputs, context)
    count = evaluate(snapshot.get("inverter_count_formula") or "panel_count", context)
    context["inverter_count"] = number(count, "Inverter Count", integer=True)
    # A show_when condition may use inverter_count; validate it after the count is available.
    for row in rows:
        visible = True if not row["show_when"] else evaluate(row["show_when"], context)
        if not isinstance(visible, bool) and not (type(visible) in (int, float) and visible in (0, 1)):
            raise RuleError(f"{row['label']}: Show When must return True, False, or a Check value (0 or 1).")
        row["is_visible"] = int(bool(visible))
        if visible and row["required"]:
            if context[row["variable_key"]] is None:
                raise RuleError(f"Enter {row['label']} in Additional Site Inputs.")
    return context, rows


def quantity_overrides(rows):
    result = {}
    for row in rows or []:
        if cint(row.get("has_quantity_override")):
            key = f"{row.get('template_alias')}.{row.get('rule_key')}"
            reason = (row.get("override_reason") or "").strip()
            if not reason:
                raise RuleError(f"{key}: enter a reason for the quantity override.")
            result[key] = {"quantity": number(row.get("quantity"), key), "reason": reason}
    return result


def valuation(item, uom, warehouse):
    stock_uom = item.stock_uom
    factor = 1.0 if uom == stock_uom else None
    if factor is None:
        for conversion in item.uoms:
            if conversion.uom == uom and flt(conversion.conversion_factor) > 0:
                factor = flt(conversion.conversion_factor)
                break
    if factor is None:
        return {"rate": 0, "conversion_factor": 0, "stock_uom": stock_uom,
                "valuation_status": "Missing Conversion"}
    rate = frappe.db.get_value("Bin", {"item_code": item.name, "warehouse": warehouse}, "valuation_rate")
    # Item.valuation_rate is still a valuation estimate, never a selling/buying price-list rate.
    rate = flt(rate) if flt(rate) > 0 else flt(item.valuation_rate)
    return {"rate": flt(rate * factor, 6), "conversion_factor": factor, "stock_uom": stock_uom,
            "valuation_status": "Valued" if rate > 0 else "Missing Valuation"}


def price_materials(rows, company, warehouse, previous_rows=None, refresh=False):
    warnings = []
    if not company:
        raise RuleError("Set the Company for material valuation.")
    frappe.has_permission("Company", doc=company, ptype="select", throw=True)
    if not warehouse:
        raise RuleError("Set a Valuation Warehouse in this proposal or Wahni Default Settings.")
    wh = frappe.get_doc("Warehouse", warehouse)
    wh.check_permission("select")
    if wh.company != company or wh.is_group or wh.disabled:
        raise RuleError("Valuation Warehouse must be an enabled non-group warehouse in the selected Company.")
    previous = {
        (r.get("template_alias"), r.get("rule_key")): r for r in previous_rows or []
    }
    items = {}
    for row in rows:
        old = previous.get((row["template_alias"], row["rule_key"]))
        if not row.get("item_code"):
            raise RuleError(f"{row['template_alias']}.{row['rule_key']}: choose an actual ERPNext Item in the template.")
        if row["item_code"] not in items:
            item = frappe.get_doc("Item", row["item_code"])
            item.check_permission("read")
            items[item.name] = item
        item = items[row["item_code"]]
        row["uom"] = row.get("uom") or item.stock_uom
        if frappe.get_cached_value("UOM", row["uom"], "must_be_whole_number"):
            number(row["quantity"], f"{item.name} quantity", integer=True)
        use_saved = old and not refresh and old.get("item_code") == item.name and old.get("uom") == row["uom"] and old.get("valuation_warehouse") == warehouse
        if not use_saved and (item.disabled or item.has_variants):
            raise RuleError(f"{item.name}: choose an enabled, non-template Item.")
        if use_saved:
            row.update({k: old.get(k) for k in ("item_name", "description", "rate", "stock_uom", "conversion_factor", "valuation_status")})
        else:
            row["item_name"] = item.item_name
            row["description"] = row.get("description") or item.description or ""
            row.update(valuation(item, row["uom"], warehouse))
        row["valuation_warehouse"] = warehouse
        row["amount"] = flt(flt(row["quantity"]) * flt(row["rate"]), 2)
        if row.get("valuation_status") != "Valued":
            warnings.append(f"{row['component_label'] or item.name}: {row['valuation_status']} ({row['uom']}).")
    return warnings


def cost_quantity(component, panel_count, capacity_kw):
    if component == "Panel Cost":
        return panel_count
    if component in ("Structure Material", "Labour Structural", "Labour Electrical"):
        return math.ceil(panel_count / 2)
    if component == "Sales Commission":
        return capacity_kw
    if component in ("Walk Way", "Ladder"):
        return 0
    return 1


def calculate_charges(doc, snapshot, previous=None):
    rows = doc.get("cost_breakdown") or []
    initial = previous is None and not rows
    if initial:
        rows = [{k: r.get(k) for k in ("cost_component", "rate", "quantity", "included", "calculation_note")}
                for r in frappe.get_cached_doc("Wahni Default Settings").table_cost_calculation]
    old = {r.get("cost_component"): r for r in (previous.get("cost_breakdown") or [])} if previous else {}
    result = []
    for source in rows:
        row = dict(source)
        component = row.get("cost_component")
        default_qty = cost_quantity(component, doc["panel_count"], doc["capacity_kw"])
        prev = old.get(component)
        if initial or row.get("quantity") is None:
            row["quantity"] = default_qty
        elif row.get("calculated_quantity") is not None and flt(row["quantity"]) == flt(row["calculated_quantity"]):
            # The last preview can be newer than the persisted document, or the
            # proposal may not have been saved yet. Advance untouched defaults.
            row["quantity"] = default_qty
        elif prev and flt(row.get("quantity")) == flt(prev.get("quantity")):
            old_default = cost_quantity(component, flt(previous.get("panel_count")), flt(previous.get("capacity_kw")))
            if flt(prev.get("quantity")) == old_default:
                row["quantity"] = default_qty
        row["calculated_quantity"] = default_qty
        if initial:
            row["included"] = int(component not in ("Walk Way", "Ladder"))
        row["rate"] = number(row.get("rate") or 0, f"{component} rate")
        row["quantity"] = number(row.get("quantity") or 0, f"{component} quantity")
        multiplier = flt(snapshot.get("cost_panel_capacity_w")) if component == "Panel Cost" else 1
        row["amount"] = flt(row["rate"] * row["quantity"] * multiplier, 2) if cint(row.get("included")) else 0
        row["calculation_note"] = (
            f"{row['quantity']:g} panels × {multiplier:g} W × rate per watt"
            if component == "Panel Cost" else f"{row['quantity']:g} × rate"
        )
        result.append(row)
    doc["cost_breakdown"] = result
    doc["other_cost"] = flt(sum(r["amount"] for r in result), 2)


def calculate(doc, previous=None, regenerate=False, reprice=False, refresh_subsidy=False):
    doc = copy.deepcopy(as_dict(doc))
    previous = as_dict(previous) if previous else None
    initial_generation = previous is None and not doc.get("configuration_snapshot")
    saved = parse_snapshot(previous.get("configuration_snapshot")) if previous else None
    fresh = regenerate or not saved or saved.get("package_name") != doc.get("package_name")
    snapshot = load_configuration(doc.get("package_name")) if fresh else saved
    if snapshot.get("version") != VERSION:
        raise RuleError("Unsupported saved configuration version. Regenerate this proposal.")
    context, inputs = system_context(snapshot, doc, doc.get("input_values"))
    package_changed = saved and saved.get("package_name") != doc.get("package_name")
    overrides = {} if regenerate or package_changed else quantity_overrides(doc.get("table_proposal_bom"))
    rows = evaluate_materials(snapshot["mappings"], context, overrides=overrides)
    settings = frappe.get_cached_doc("Wahni Default Settings")
    company = doc.get("company") or settings.costing_company or frappe.defaults.get_user_default("Company")
    warehouse = doc.get("valuation_warehouse") or settings.valuation_warehouse
    if not warehouse and company and frappe.get_meta("Company").has_field("default_warehouse"):
        warehouse = frappe.get_cached_value("Company", company, "default_warehouse")
    refresh_rates = bool(fresh or reprice or (previous and (
        previous.get("company") != company or previous.get("valuation_warehouse") != warehouse
    )))
    warnings = price_materials(rows, company, warehouse,
        previous_rows=previous.get("table_proposal_bom") if previous else None,
        refresh=refresh_rates)
    if context["actual_capacity_kw"] < context["capacity_kw"]:
        warnings.append("The chosen panel count provides less installed panel capacity than the requested system capacity.")
    doc.update({
        "configuration_snapshot": snapshot, "calculation_version": VERSION,
        "system_name": snapshot["system_name"], "brand": snapshot["brand"],
        "system_type": snapshot["system_type"], "grid_type": snapshot["grid_type"],
        "allow_battery": cint(snapshot["allow_battery"]), "include_battery": cint(context["include_battery"]),
        "suggested_panel_count": context["suggested_panel_count"], "panel_count": context["panel_count"],
        "capacity_kw": context["capacity_kw"], "panel_capacity_w": context["panel_capacity_w"],
        "inverter_count": context["inverter_count"], "actual_capacity_kw": context["actual_capacity_kw"],
        "input_values": inputs, "company": company, "valuation_warehouse": warehouse,
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "table_proposal_bom": rows, "material_cost": flt(sum(r["amount"] for r in rows), 2),
        "costing_status": "Complete" if all(r["valuation_status"] == "Valued" for r in rows) else "Missing Valuation / Conversion",
        "calculation_warnings": "\n".join(warnings),
    })
    if fresh:
        doc["last_generated_on"] = now_datetime()
    if refresh_rates:
        doc["pricing_refreshed_on"] = now_datetime()
    calculate_charges(doc, snapshot, previous)
    if initial_generation or refresh_subsidy or doc.get("subsidy") is None:
        doc["subsidy"] = next((flt(r.get("subsidy_amount")) for r in snapshot["subsidy_rules"]
            if flt(r.get("capacity_from")) <= context["capacity_kw"] <= flt(r.get("capacity_to"))), 0)
    discount = number(doc.get("discount") or 0, "Discount")
    subsidy = number(doc.get("subsidy") or 0, "Subsidy")
    doc["project_cost"] = flt(doc["material_cost"] + doc["other_cost"], 2)
    doc["final_amount"] = flt(doc["project_cost"] - discount - subsidy, 2)
    return doc


RESULT_FIELDS = (
    "configuration_snapshot", "calculation_version", "system_name", "brand", "system_type", "grid_type",
    "allow_battery", "include_battery", "suggested_panel_count", "panel_count", "capacity_kw", "panel_capacity_w",
    "inverter_count", "actual_capacity_kw", "input_values", "company", "valuation_warehouse", "currency",
    "table_proposal_bom", "material_cost", "costing_status", "calculation_warnings", "last_generated_on",
    "pricing_refreshed_on", "cost_breakdown", "other_cost", "project_cost", "final_amount", "subsidy",
)


def apply_result(document, result):
    for key in RESULT_FIELDS:
        document.set(key, result.get(key))
