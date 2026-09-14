"""Permission-aware resolution of Project report inputs."""

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import frappe
from frappe.utils import cint

from wahni_solar.solar_project.constants import ANNEXURES, LEGACY_PANEL_CATEGORIES, LIBRARY_CATEGORIES, OPTIONAL_SECTIONS, PANEL_DOCUMENT, SECTIONS


def read_file(url):
    if not url or not url.startswith(("/files/", "/private/files/")):
        raise ValueError("Upload a local ERPNext file; external file URLs are not supported.")
    for name in frappe.get_all("File", filters={"file_url": url, "is_folder": 0}, pluck="name"):
        file = frappe.get_doc("File", name)
        if not file.has_permission("read"):
            continue
        path = Path(file.get_full_path()).resolve()
        roots = [Path(frappe.get_site_path("public", "files")).resolve(),
                 Path(frappe.get_site_path("private", "files")).resolve()]
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError("The attachment is outside the site's files directory.")
        content = file.get_content()
        if isinstance(content, str):
            content = content.encode("utf-8")
        return content, {"file": file.name, "file_url": file.file_url,
                         "sha256": hashlib.sha256(content).hexdigest()}
    frappe.throw("The attached file is missing or you do not have permission to read it.", frappe.PermissionError)


def select_bank(accounts):
    defaults = [account for account in accounts if account.get("is_default")]
    if len(defaults) == 1:
        return defaults[0]
    if not defaults and len(accounts) == 1:
        return accounts[0]
    return None


def select_annexure(files, number):
    """Files must already be restricted to one Grid Check, newest first.

    Accept generated, renamed and hash-suffixed filenames, including Roman
    numerals. Never search the global File table by consumer name or filename.
    """
    pattern = re.compile(r"(?<![a-z])ann?exure[\s_.-]*(?:no[\s_.-]*)?(iii|ii|i|[123])(?![a-z0-9])", re.I)
    numbers = {"i": 1, "ii": 2, "iii": 3, "1": 1, "2": 2, "3": 3}
    seen = set()
    for file in files:
        url = file.get("file_url")
        if not url or url in seen:
            continue
        seen.add(url)
        names = [unquote(file.get("file_name") or ""), unquote(urlsplit(url).path.rsplit("/", 1)[-1])]
        matches = {numbers[match.group(1).lower()] for name in names if name.lower().endswith(".pdf")
                   for match in pattern.finditer(name)}
        if matches == {number}:
            return file
    return None


def select_library(entries, category, brand, item_codes, panel_watt_peak=None):
    brand = (brand or "").strip().casefold()
    if category == PANEL_DOCUMENT:
        if not brand or cint(panel_watt_peak) <= 0:
            return None, "Set the linked Solar Proposal's panel brand and select a Panel Item on the Project with a positive Watt Peak (Wp)."
        matches = [entry for entry in entries if entry.category == category
                   and (entry.brand or "").strip().casefold() == brand
                   and cint(entry.get("panel_watt_peak")) == cint(panel_watt_peak)]
        if not matches:
            return None, f"No combined panel datasheet/BIS matches {brand} and {cint(panel_watt_peak)} Wp."
        if len(matches) != 1:
            return None, "Several combined panel documents match this brand and Wp. Disable duplicates or upload a Project override."
        return matches[0], None
    matches = []
    for entry in entries:
        if entry.category != category:
            continue
        if entry.brand and entry.brand.strip().casefold() != brand:
            continue
        if entry.model and entry.model not in item_codes:
            continue
        matches.append((2 * bool(entry.model) + bool(entry.brand), entry))
    if not matches:
        return None, None
    highest = max(score for score, _ in matches)
    best = [entry for score, entry in matches if score == highest]
    if len(best) != 1:
        return None, "Several library documents match. Disable duplicates or upload a Project override."
    return best[0], None


def resolve_customer_address(customer, linked, warnings):
    if not customer:
        return None
    try:
        if customer.get("customer_primary_address"):
            return linked("Address", customer.customer_primary_address)
        addresses = frappe.get_list("Address", filters=[
            ["Dynamic Link", "parenttype", "=", "Address"],
            ["Dynamic Link", "link_doctype", "=", "Customer"],
            ["Dynamic Link", "link_name", "=", customer.name],
        ], fields=["name", "is_primary_address"], limit_page_length=0)
        primary = [address for address in addresses if address.get("is_primary_address")]
        candidates = primary or addresses
        if len(candidates) == 1:
            return linked("Address", candidates[0].name)
        if candidates:
            warnings.append("Several customer addresses match. Set a primary address to use its city and county for the SLD location.")
    except (frappe.PermissionError, frappe.DoesNotExistError):
        warnings.append("Customer address is unavailable; the SLD location uses the KSEB address.")
    return None


def resolve_context(project_name):
    project = frappe.get_doc("Project", project_name)
    project.check_permission("read")
    refs = [{"doctype": "Project", "name": project.name}]
    warnings = []

    def linked(doctype, name):
        if not name:
            return None
        doc = frappe.get_doc(doctype, name)
        doc.check_permission("read")
        refs.append({"doctype": doctype, "name": name})
        return doc

    customer = linked("Customer", project.customer)
    address = resolve_customer_address(customer, linked, warnings)
    lead = linked("Lead", customer.get("lead_name") if customer else None)
    proposal = linked("Solar Proposal", project.get("custom_solar_proposal"))
    if proposal and proposal.lead and (not lead or proposal.lead != lead.name):
        frappe.throw("The Solar Proposal Lead does not match the Project customer's Lead.")
    package = linked("Solar Package", proposal.package_name if proposal else None)
    panel_item = linked("Item", project.get("custom_panel_item"))
    if panel_item and panel_item.item_group != "Panel":
        frappe.throw("Select a Panel Item from the Panel item group.")
    grids = frappe.get_list("KSEB Grid Check", filters={"lead": lead.name}, pluck="name",
                           limit_page_length=0) if lead else []
    grid_name = project.get("custom_report_grid_check")
    if not grid_name and len(grids) == 1:
        grid_name = grids[0]
    grid = linked("KSEB Grid Check", grid_name)
    if grid and (not lead or grid.lead != lead.name):
        frappe.throw("The selected Grid Check must belong to the Project customer's Lead.")
    if not grid:
        warnings.append("Select a Report KSEB Grid Check." if grids else "No accessible KSEB Grid Check is linked.")

    bank = None
    if customer:
        try:
            accounts = frappe.get_list("Bank Account", filters={"party_type": "Customer", "party": customer.name,
                                       "disabled": 0, "is_company_account": 0},
                                       fields=["name", "is_default"], limit_page_length=0)
            selected = select_bank(accounts)
            if selected:
                bank = linked("Bank Account", selected.name)
            elif accounts:
                warnings.append("Several customer bank accounts match; template bank values were retained.")
        except frappe.PermissionError:
            warnings.append("Customer bank information is not accessible; template bank values were retained.")

    invoice = linked("Sales Invoice", project.get("custom_report_sales_invoice"))
    if invoice and (invoice.project != project.name or invoice.customer != project.customer
                    or invoice.docstatus != 1 or invoice.is_return):
        frappe.throw("Select a submitted, non-return Sales Invoice for this Project and customer.")
    if not invoice and customer:
        try:
            invoices = frappe.get_list("Sales Invoice", filters={"project": project.name, "customer": customer.name,
                                      "docstatus": 1, "is_return": 0}, pluck="name", limit_page_length=0)
            if len(invoices) == 1:
                invoice = linked("Sales Invoice", invoices[0])
            elif len(invoices) > 1:
                warnings.append("Several invoices match. Select a Report Sales Invoice to include one.")
        except frappe.PermissionError:
            warnings.append("Sales Invoices are not accessible; invoice skipped.")

    def fields(doc, names):
        return {key: doc.get(key) for key in ("name", *names.split())} if doc else {}

    context = {
        "project": project.name,
        "panel_item": panel_item.name if panel_item else None,
        "panel_watt_peak": panel_item.get("custom_panel_watt_peak") if panel_item else None,
        "customer_address": fields(address, "city county"),
        "grid": fields(grid, "consumer_name consumer_no customer_address registered_mobile division subdivision section tariff connected_load proposed_solar_capacity phase"),
        "lead": fields(lead, "email_id mobile_no phone"),
        "proposal": fields(proposal, "capacity_kw panel_count panel_brand"),
        "package": fields(package, "brand grid_type system_type connection_type"),
        "bank": fields(bank, "account_name bank bank_account_no branch_code"),
        "permissions": refs,
        "warnings": warnings,
    }
    library = frappe.get_list("Project Report Document", filters={"enabled": 1},
                              fields=["name", "category", "brand", "model", "panel_watt_peak", "file", "page_from", "page_to"],
                              limit_page_length=0)
    overrides = {row.category: row.file for row in project.get("custom_report_attachments", []) if row.file}
    if any(category in overrides for category in LEGACY_PANEL_CATEGORIES) or any(
            entry.category in LEGACY_PANEL_CATEGORIES for entry in library):
        warnings.append("Separate Panel Datasheet/Panel BIS entries are no longer selected. Upload a Panel Datasheet and BIS PDF with its brand and Wp, or a combined Project override.")
    items = project.get("custom_table_project_bom") or (proposal.get("table_proposal_bom") if proposal else [])
    item_codes = {row.item_code for row in items or []}
    grid_files = frappe.get_all("File", filters={"attached_to_doctype": "KSEB Grid Check",
                               "attached_to_name": grid.name, "is_folder": 0},
                               fields=["file_name", "file_url"], order_by="creation desc, name desc") if grid else []
    sources = []
    for category in LIBRARY_CATEGORIES:
        source = {"category": category}
        if category in overrides:
            source.update(url=overrides[category], origin="Project upload", doctype="Project", name=project.name)
        elif category in ANNEXURES:
            if grid:
                match = select_annexure(grid_files, ANNEXURES[category])
                if match:
                    source.update(url=match.file_url, origin="KSEB Grid Check", doctype="KSEB Grid Check", name=grid.name)
                else:
                    source.update(annexure_number=ANNEXURES[category], origin="KSEB Grid Check",
                                  doctype="KSEB Grid Check", name=grid.name)
        elif category == "Sales Invoice":
            if invoice:
                source.update(invoice=invoice.name, origin="Sales Invoice", doctype="Sales Invoice", name=invoice.name)
        else:
            brand = (proposal.get("panel_brand") if proposal else None) if category.startswith("Panel ") else (package.brand if package else None)
            entry, reason = select_library(library, category, brand, item_codes, context["panel_watt_peak"])
            if entry:
                source.update(url=entry.file, origin="Library", doctype="Project Report Document", name=entry.name,
                              page_from=entry.page_from, page_to=entry.page_to)
                if category == PANEL_DOCUMENT:
                    source.update(brand=entry.brand, panel_watt_peak=entry.panel_watt_peak)
            elif reason:
                source["reason"] = reason
        if not source.get("url") and not source.get("invoice") and not source.get("annexure_number"):
            source.setdefault("reason", "No document available.")
        sources.append(source)
    context["sources"] = sources
    context["grid_choices"] = grids
    return context


def public_context(context):
    """No bank details or internal snapshot data are sent to the Project dialog."""
    return {"grid_choices": context["grid_choices"], "warnings": context["warnings"],
            "documents": [{"category": source["category"], "available": bool(source.get("url") or source.get("invoice") or source.get("annexure_number")),
                           "will_generate": bool(source.get("annexure_number")),
                           "origin": source.get("origin"), "reason": source.get("reason"),
                           "optional": source["category"] in OPTIONAL_SECTIONS}
                          for source in context["sources"] if source["category"] in SECTIONS]}
