"""Create a Sales Order from a Project's material list (custom_table_project_bom)."""

import frappe
from frappe.model.mapper import get_mapped_doc


def _uses_valuation_rates(project):
    if any(row.get("source_template") for row in project.get("custom_table_project_bom") or []):
        return True
    proposal = project.get("custom_solar_proposal")
    return bool(proposal and frappe.db.get_value("Solar Proposal", proposal, "calculation_version") == "Templates v1")


@frappe.whitelist()
def get_project_materials(source_name):
    project = frappe.get_doc("Project", source_name)
    project.check_permission("read")
    return {
        "items": [
            {key: row.get(key) for key in ("item_code", "quantity", "uom", "rate")}
            for row in project.get("custom_table_project_bom") or [] if row.item_code
        ],
        "use_selling_prices": _uses_valuation_rates(project),
    }


@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
    use_selling_prices = None

    def set_item_rate(source, target, project):
        nonlocal use_selling_prices
        if use_selling_prices is None:
            use_selling_prices = _uses_valuation_rates(project)
        if use_selling_prices:
            # None lets ERPNext fill these values using the selling context.
            # A valuation estimate must never become a customer's sales rate.
            target.rate = None
            target.price_list_rate = None
        else:
            target.rate = source.get("rate")

    def set_missing_values(source, target):
        if not source.customer:
            frappe.throw(frappe._("Set a Customer on Project {0} before creating a Sales Order.").format(source.name))
        target.run_method("set_missing_values")
        target.run_method("calculate_taxes_and_totals")

    return get_mapped_doc("Project", source_name, {
        "Project": {
            "doctype": "Sales Order",
            "field_map": {"name": "project"},
            "field_no_map": ["status", "naming_series"],
        },
        "Solar Proposal BOM Item": {
            "doctype": "Sales Order Item",
            "field_map": {"quantity": "qty"},
            "field_no_map": ["amount", "rate"],
            "condition": lambda row: bool(row.item_code),
            "postprocess": set_item_rate,
        },
    }, target_doc, set_missing_values)
