"""Separate app module ownership and leave the singular Site Visit route to its DocType."""

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
    # Never alter the legacy module's placement/navigation on a Masters site.
    if frappe.db.get_value("Module Def", "Solar Monitor", "app_name") == "wahni_solar":
        for doctype in ("DocType", "Workspace", "Page", "Sidebar", "Custom Sidebar"):
            if frappe.db.exists("DocType", doctype) and frappe.get_meta(doctype).has_field("module"):
                frappe.db.set_value(doctype, {"module": "Solar Monitor"}, "module", "Wahni Solar Monitor", update_modified=False)
        # Keep the old row (and any links) rather than deleting a Module Def,
        # whose on_trash can remove navigation and developer-mode source files.
        frappe.db.set_value("Module Def", "Solar Monitor", "app_name", None, update_modified=False)

    old_workspace = frappe.db.get_value("Workspace", "Site Visit", ["module", "standard"], as_dict=True)
    workspace = old_workspace or frappe.db.get_value("Workspace", "Site Visits", ["module", "standard"], as_dict=True)
    if workspace and workspace.module == "Site Visit" and workspace.standard:
        if old_workspace:
            rename_doc(
                "Workspace", "Site Visit", "Site Visits", force=True,
                ignore_permissions=True, show_alert=False, rebuild_search=False,
            )
        # Desk routes use the title, not just the document name. A rename leaves
        # the title unchanged, and timestamp-based sync may skip an older JSON.
        frappe.db.set_value("Workspace", "Site Visits", {"title": "Site Visits", "label": "Site Visits"}, update_modified=False)
    frappe.clear_cache()
