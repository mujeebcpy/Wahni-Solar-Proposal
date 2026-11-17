"""Site Visit and PMS Visit APIs for the Wahni Field PWA.

Lists show only visits assigned to the session Employee (assignment truth is the
employee Link, never the owner). Forms are metadata driven: effective DocType
meta (custom fields, property setters, permlevels) supplies fields, while
VISIT_CONFIG supplies mobile steps and fields the portal must never edit.
Saves go through the normal controllers and permissions.
"""

import frappe
from frappe import _
from frappe.utils import cint

from wahni_solar.field_portal.access import ASSIGNEE_FIELDS, require_field_user
from wahni_solar.field_portal.utils import (
    attachments,
    ensure_not_stale,
    idempotent_insert,
    parse,
    remove_attachment,
)

LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Button", "Fold"}
ATTACH_TYPES = {"Attach", "Attach Image"}
# Field types the mobile renderer supports; others are shown as "edit in Desk".
SUPPORTED_TYPES = {
    "Data", "Small Text", "Text", "Long Text", "Select", "Int", "Float", "Currency", "Percent",
    "Date", "Check", "Attach", "Attach Image", "Geolocation", "Link", "Phone",
}
STATUSES = ("Assigned", "In Progress", "Completed")

VISIT_CONFIG = {
    "Site Visit": {
        "route": "site-visits",
        "protected": {"solar_proposal", "lead", "customer", "company", "currency", "lead_owner",
                      "lead_source", "site_visit_by", "status"},
        "steps": [
            ("customer", "Customer", ["visit_details", "basic_information", "documentation_requirements"]),
            ("location", "Location", ["site_location"]),
            ("site", "Site Details", ["site_visit_remarks"]),
            ("measurements", "Measurements", ["measurements_and_status"]),
            ("drawings", "Drawings", ["drawings"]),
        ],
        "list_fields": ["name", "status", "customer_name", "location", "contact_number", "visit_date",
                        "requested_capacity_kw", "solar_proposal", "modified"],
        "search_fields": ["name", "customer_name", "location", "solar_proposal"],
        "context_fields": ["solar_proposal", "customer_name", "contact_number", "consumer_phone_number",
                           "address", "location", "landmark", "pincode", "geolocation", "visit_date"],
    },
    "PMS Visit": {
        "route": "pms-visits",
        "protected": {"service_person", "service_person_name", "project", "customer", "status",
                      "legacy_site_data_collection"},
        "steps": [
            ("details", "Visit Details", ["visit_details"]),
            ("photos", "Photos", ["inspection"]),
            ("remarks", "Remarks", ["remarks_section"]),
        ],
        "list_fields": ["name", "status", "client_name", "customer", "project", "place", "pms_date",
                        "plant_capacity_kw", "modified"],
        "search_fields": ["name", "client_name", "customer", "project", "place"],
        "context_fields": ["project", "customer", "client_name", "place", "site_location_link", "pms_date"],
    },
}


def config(doctype):
    if doctype not in VISIT_CONFIG:
        frappe.throw(_("Unsupported visit type."))
    return VISIT_CONFIG[doctype]


def own_visit(doctype, name, employee):
    """A visit assigned to the session employee (the portal never shows others)."""
    config(doctype)
    doc = frappe.get_doc(doctype, name)
    if doc.get(ASSIGNEE_FIELDS[doctype]) != employee:
        raise frappe.PermissionError(_("This visit is not assigned to you."))
    doc.check_permission("read")
    return doc


def form_fields(doc):
    """Effective, permission-filtered field metadata grouped into mobile steps."""
    meta = frappe.get_meta(doc.doctype)
    read_levels = set(meta.get_permlevel_access("read"))
    write_levels = set(meta.get_permlevel_access("write"))
    editable_doc = doc.has_permission("write")
    cfg = config(doc.doctype)
    step_of_section = {section: key for key, _label, sections in cfg["steps"] for section in sections}
    section, step = None, cfg["steps"][0][0]
    fields = []
    for df in meta.fields:
        if df.fieldtype == "Section Break":
            section = df.fieldname
            step = step_of_section.get(section, "additional")
            continue
        if df.fieldtype in LAYOUT_TYPES or df.hidden or df.permlevel not in read_levels:
            continue
        writable = (
            editable_doc and df.permlevel in write_levels and not df.read_only
            and df.fieldname not in cfg["protected"]
        )
        fields.append({
            "fieldname": df.fieldname, "fieldtype": df.fieldtype, "label": _(df.label) if df.label else df.fieldname,
            "options": df.options, "reqd": cint(df.reqd), "read_only": not writable,
            "depends_on": df.depends_on, "mandatory_depends_on": df.mandatory_depends_on,
            "read_only_depends_on": df.read_only_depends_on, "description": _(df.description) if df.description else None,
            "step": step, "section": section, "supported": df.fieldtype in SUPPORTED_TYPES,
        })
    steps = [{"key": key, "label": _(label)} for key, label, _sections in cfg["steps"]]
    if any(field["step"] == "additional" for field in fields):
        steps.append({"key": "additional", "label": _("Additional Details")})
    return steps, fields


def writable_fields(doc):
    return {
        field["fieldname"] for field in form_fields(doc)[1]
        if not field["read_only"] and field["supported"] and field["fieldtype"] not in ATTACH_TYPES
    }


def visit_payload(doc):
    steps, fields = form_fields(doc)
    assignee_field = ASSIGNEE_FIELDS[doc.doctype]
    values = {field["fieldname"]: doc.get(field["fieldname"]) for field in fields}
    employee = doc.get(assignee_field)
    return {
        "doctype": doc.doctype, "name": doc.name, "status": doc.status, "modified": doc.modified,
        "owner": doc.owner, "assignee": employee,
        "assignee_name": frappe.db.get_value("Employee", employee, "employee_name") if employee else None,
        "context": {field: doc.get(field) for field in config(doc.doctype)["context_fields"]},
        "steps": steps, "fields": fields, "values": values,
        "editable": bool(doc.has_permission("write")),
        "attachments": attachments(doc),
    }


@frappe.whitelist(methods=["GET"])
def list_visits(doctype, status=None, txt=None, start=0, page_length=20):
    employee = require_field_user()
    cfg = config(doctype)
    filters = {ASSIGNEE_FIELDS[doctype]: employee}
    if status in STATUSES:
        filters["status"] = status
    elif status == "open":
        filters["status"] = ["in", ["Assigned", "In Progress"]]
    or_filters = {field: ["like", f"%{txt}%"] for field in cfg["search_fields"]} if txt else None
    return frappe.get_list(
        doctype, fields=cfg["list_fields"], filters=filters, or_filters=or_filters,
        order_by="modified desc", limit_start=max(0, cint(start)),
        limit_page_length=min(50, max(1, cint(page_length) or 20)),
    )


@frappe.whitelist(methods=["GET"])
def get_visit(doctype, name):
    return visit_payload(own_visit(doctype, name, require_field_user()))


@frappe.whitelist(methods=["POST"])
def save_visit(doctype, name, values, modified=None, action="save"):
    """Save progress (Assigned -> In Progress) or complete, via the normal controller."""
    employee = require_field_user()
    doc = own_visit(doctype, name, employee)
    ensure_not_stale(doc, modified)
    values = parse(values)
    allowed = writable_fields(doc)
    rejected = sorted(set(values) - allowed - {"name", "modified"})
    for fieldname in allowed & set(values):
        doc.set(fieldname, values[fieldname])
    if action == "complete":
        doc.status = "Completed"
    elif action == "save":
        if doc.status == "Assigned":
            doc.status = "In Progress"
    else:
        frappe.throw(_("Unknown action."))
    doc.save()
    doc.reload()  # return stored (typed) values
    payload = visit_payload(doc)
    payload["ignored_fields"] = rejected
    return payload


@frappe.whitelist(methods=["POST"])
def set_attachment(doctype, name, fieldname, file_url, modified=None):
    """Bind an uploaded private file to an Attach field, without touching other edits."""
    employee = require_field_user()
    doc = own_visit(doctype, name, employee)
    ensure_not_stale(doc, modified)
    field = next((f for f in form_fields(doc)[1] if f["fieldname"] == fieldname), None)
    if not field or field["read_only"] or field["fieldtype"] not in ATTACH_TYPES:
        frappe.throw(_("This file field cannot be changed."), frappe.PermissionError)
    file = frappe.db.get_value(
        "File", {"file_url": file_url, "attached_to_doctype": doctype, "attached_to_name": name, "is_private": 1},
        ["name", "owner"], as_dict=True,
    )
    if not file:
        frappe.throw(_("Upload the file to this visit as a private file first."))
    previous = doc.get(fieldname)
    doc.set(fieldname, file_url)
    if doc.status == "Assigned":
        doc.status = "In Progress"
    doc.save()
    if previous and previous != file_url:
        discard_unreferenced(doc, previous)
    return visit_payload(doc)


@frappe.whitelist(methods=["POST"])
def clear_attachment(doctype, name, fieldname, modified=None):
    employee = require_field_user()
    doc = own_visit(doctype, name, employee)
    ensure_not_stale(doc, modified)
    field = next((f for f in form_fields(doc)[1] if f["fieldname"] == fieldname), None)
    if not field or field["read_only"] or field["fieldtype"] not in ATTACH_TYPES:
        frappe.throw(_("This file field cannot be changed."), frappe.PermissionError)
    previous = doc.get(fieldname)
    doc.set(fieldname, None)
    doc.save()
    if previous:
        discard_unreferenced(doc, previous)
    return visit_payload(doc)


@frappe.whitelist(methods=["POST"])
def discard_upload(doctype, name, file_name):
    """Delete an upload that was never bound to a field (cancelled/abandoned)."""
    doc = own_visit(doctype, name, require_field_user())
    file_url = frappe.db.get_value("File", file_name, "file_url")
    if file_url and any(doc.get(f) == file_url for f in fieldnames_of_type(doc, ATTACH_TYPES)):
        frappe.throw(_("This file is still used by the visit."))
    remove_attachment(doc, file_name)
    return {"ok": True}


def fieldnames_of_type(doc, types):
    return [df.fieldname for df in frappe.get_meta(doc.doctype).fields if df.fieldtype in types]


def discard_unreferenced(doc, file_url):
    """Remove a replaced file only if no field of this visit still references it."""
    if any(doc.get(f) == file_url for f in fieldnames_of_type(doc, ATTACH_TYPES)):
        return
    for file_name in frappe.get_all(
        "File", filters={"file_url": file_url, "attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
        pluck="name",
    ):
        remove_attachment(doc, file_name)


@frappe.whitelist(methods=["GET"])
def search_proposals(txt=None, start=0, page_length=20):
    """Solar Proposals without a Site Visit, for self-created visits: (name, customer) only."""
    require_field_user()
    from wahni_solar.site_visit.api import proposal_query

    rows = proposal_query("Solar Proposal", txt or "", "name", start, page_length, {})
    return [{"name": row[0], "customer_name": row[1]} for row in rows]


@frappe.whitelist(methods=["POST"])
def create_site_visit(solar_proposal, client_token=None):
    """Self-assigned Site Visit for a proposal, or the existing one if it is already yours."""
    employee = require_field_user()
    from wahni_solar.site_visit.api import make_site_visit

    visit = make_site_visit(solar_proposal)
    if not visit.is_new():
        if visit.site_visit_by == employee:
            return {"name": visit.name, "existing": True}
        frappe.throw(_("A Site Visit already exists for this Solar Proposal."), frappe.DuplicateEntryError)

    def build():
        visit.site_visit_by = employee  # the portal always self-assigns
        return visit

    return {"name": idempotent_insert(client_token, build).name, "existing": False}


@frappe.whitelist(methods=["GET"])
def search_completed_projects(txt=None, start=0, page_length=20):
    """Completed Projects the user may select (several PMS visits per Project are allowed)."""
    require_field_user()
    or_filters = {"name": ["like", f"%{txt}%"], "project_name": ["like", f"%{txt}%"],
                  "customer": ["like", f"%{txt}%"]} if txt else None
    rows = frappe.get_list(
        "Project", fields=["name", "project_name", "customer"], filters={"status": "Completed"},
        or_filters=or_filters, order_by="modified desc", limit_start=max(0, cint(start)),
        limit_page_length=min(50, max(1, cint(page_length) or 20)),
    )
    customers = {row.customer for row in rows if row.customer}
    names = dict(frappe.get_all("Customer", filters={"name": ["in", list(customers)]},
                                fields=["name", "customer_name"], as_list=True)) if customers else {}
    for row in rows:
        row.customer_name = names.get(row.customer)
    return rows


@frappe.whitelist(methods=["POST"])
def create_pms_visit(project, client_token=None):
    """Self-assigned PMS Visit for a completed Project; the controller fills Project defaults."""
    employee = require_field_user()

    def build():
        return frappe.get_doc({"doctype": "PMS Visit", "project": project, "service_person": employee})

    return {"name": idempotent_insert(client_token, build).name}
