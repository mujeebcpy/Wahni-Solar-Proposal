"""Create a Sales Order from a Project's material list (custom_table_project_bom)."""

import frappe
from frappe.model.mapper import get_mapped_doc


@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
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
            "field_no_map": ["amount"],
            "condition": lambda row: bool(row.item_code),
        },
    }, target_doc, set_missing_values)
