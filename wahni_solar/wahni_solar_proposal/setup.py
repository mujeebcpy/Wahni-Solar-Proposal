"""Install the current proposal format and optional editable demo configuration."""

import frappe

from wahni_solar.wahni_solar_proposal.demo import SETTINGS, seed_demo_configuration


def set_costing_defaults():
    settings = frappe.get_single(SETTINGS)
    warehouses = frappe.get_all("Warehouse", filters={"is_group": 0, "disabled": 0, "is_rejected_warehouse": 0},
                                fields=["name", "company", "warehouse_name"], order_by="name")
    by_name = {row["name"]: row for row in warehouses}
    stock_default = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    company = settings.costing_company
    if not company:
        preferred = frappe.defaults.get_global_default("company")
        companies = {row["company"] for row in warehouses if row.get("company")}
        if preferred in companies:
            company = preferred
        elif stock_default in by_name:
            company = by_name[stock_default]["company"]
        elif len(companies) == 1:
            company = next(iter(companies))
        if company:
            frappe.db.set_single_value(SETTINGS, "costing_company", company)

    if company and not settings.valuation_warehouse:
        candidates = [row for row in warehouses if row["company"] == company]
        candidates.sort(key=lambda row: (not row["warehouse_name"].lower().startswith("stores"), row["name"]))
        chosen = by_name.get(stock_default)
        if not chosen or chosen["company"] != company:
            chosen = candidates[0] if candidates else None
        if chosen:
            frappe.db.set_single_value(SETTINGS, "valuation_warehouse", chosen["name"])
            return []
    if not company or not (settings.valuation_warehouse or any(row["company"] == company for row in warehouses)):
        return ["Select a costing company and its leaf valuation warehouse in Wahni Default Settings."]
    return []


def after_migrate():
    notes = set_costing_defaults()
    # Standard app-managed print formats must update even when a site has a newer timestamp.
    frappe.reload_doc("wahni_solar_proposal", "print_format", "solar_proposal", force=True)
    report = seed_demo_configuration()
    notes.extend(report["warnings"])
    if report["packages"]:
        notes.append("Demo packages: " + ", ".join(report["packages"]))
    frappe.db.set_single_value(SETTINGS, "demo_setup_note", "\n".join(notes))
    return report
