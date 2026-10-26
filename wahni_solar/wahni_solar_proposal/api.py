"""Permission-checked previews for the package and proposal editors."""

import frappe

from wahni_solar.wahni_solar_proposal import configuration
from wahni_solar.wahni_solar_proposal.rules import RuleError, evaluate_materials


def proposal_document(value):
    value = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(value, dict) or value.get("doctype") != "Solar Proposal":
        frappe.throw("Expected a Solar Proposal document.")
    doc = frappe.get_doc(value)
    previous = None
    if doc.name and frappe.db.exists("Solar Proposal", doc.name):
        previous = frappe.get_doc("Solar Proposal", doc.name)
        previous.check_permission("write")
    else:
        doc.check_permission("create")
    return doc, previous


@frappe.whitelist()
def preview_package(package_name, values=None):
    values = frappe.parse_json(values) if isinstance(values, str) else values
    values = values or {}
    try:
        snapshot = configuration.load_configuration(package_name)
        supplied = [{"variable_key": key, "value": values[key]}
                    for key in (d["variable_key"] for d in snapshot["input_definitions"]) if key in values]
        context, inputs = configuration.system_context(snapshot, values, supplied)
        rows = evaluate_materials(snapshot["mappings"], context, include_excluded=True)
        return {"rows": rows, "context": context, "input_values": inputs, "warnings": [],
                "suggested_panel_count": context["suggested_panel_count"],
                "panel_count": context["panel_count"], "inverter_count": context["inverter_count"]}
    except RuleError as error:
        frappe.throw(str(error), title="Configuration rule error")


@frappe.whitelist()
def package_inputs(package_name, supplied=None):
    """Bootstrap input controls before required values can be calculated."""
    snapshot = configuration.load_configuration(package_name)
    supplied = frappe.parse_json(supplied) if isinstance(supplied, str) else supplied
    values = {r.get("variable_key"): r.get("value") for r in supplied or []}
    return [{
        **{key: row.get(key) for key in (
            "variable_key", "label", "input_type", "uom", "select_options", "show_when", "required"
        )},
        "value": values.get(row["variable_key"], row.get("default_value") or ""),
        "is_visible": 1,
    } for row in snapshot["input_definitions"]]


@frappe.whitelist()
def install_demo_defaults():
    frappe.only_for("System Manager")
    from wahni_solar.wahni_solar_proposal.demo import seed_demo_configuration

    frappe.db.set_single_value("Wahni Default Settings", "demo_defaults_cleared", 0)
    return seed_demo_configuration()


@frappe.whitelist()
def preview_proposal(doc, refresh_subsidy=False):
    document, previous = proposal_document(doc)
    try:
        result = configuration.calculate(document, previous=previous,
            refresh_subsidy=bool(frappe.utils.cint(refresh_subsidy)))
        return {key: result.get(key) for key in configuration.RESULT_FIELDS}
    except RuleError as error:
        frappe.throw(str(error), title="Configuration rule error")
