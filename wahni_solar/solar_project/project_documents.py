"""Stored document-specific inputs and permission-aware, live print context."""

import json
import re

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from wahni_solar.solar_project.documents import form_values, panel_watt_peak, text


DOCUMENT_TYPES = {
    "Customer Vendor Agreement": "Customer Vendor Agreement",
    "KSEB Agreement": "Customer KSEB Agreement",
    "Check List": "Solar Installation Checklist",
    "Project Completion Report": "Solar Completion Certificate",
}
PRINT_FORMATS = {category: doctype for category, doctype in DOCUMENT_TYPES.items()}
LAYOUT_FIELDTYPES = ("Section Break", "Column Break", "HTML", "Tab Break")
# Formatted from stored dates; edit the date field instead.
NOT_OVERRIDABLE = {"date", "date_month_year"}


def stored_fieldnames(doc):
    return [field.fieldname for field in doc.meta.fields
            if field.fieldtype not in LAYOUT_FIELDTYPES and field.fieldname not in ("project", "overrides")]


def parse_overrides(value):
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def category_for(doctype):
    for category, candidate in DOCUMENT_TYPES.items():
        if candidate == doctype:
            return category
    frappe.throw("Unsupported Project document type.")


def ensure_documents(project, categories=None):
    """Serialize creation on Project; unique Project fields also protect Desk inserts."""
    frappe.get_doc("Project", project).check_permission("write")
    frappe.db.sql("SELECT name FROM `tabProject` WHERE name=%s FOR UPDATE", (project,))
    result = {}
    for category in categories if categories is not None else DOCUMENT_TYPES:
        doctype = DOCUMENT_TYPES[category]
        name = frappe.db.get_value(doctype, {"project": project}, "name", for_update=True)
        if name:
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("read")
        else:
            doc = frappe.new_doc(doctype)
            doc.project = project
            # Project write permission authorizes automatic creation. The controller
            # checks it again; this does not grant access to linked source records.
            doc.insert(ignore_permissions=True)
        result[category] = doc
    return result


def get_document(project, category):
    """The saved record when one exists; otherwise an unsaved record with defaults.
    Printing never creates records; Project Documents opens one for editing."""
    doctype = DOCUMENT_TYPES[category]
    name = frappe.db.get_value(doctype, {"project": project}, "name")
    if name:
        doc = frappe.get_doc(doctype, name)
    else:
        doc = frappe.new_doc(doctype)
        doc.project = project
    doc.check_permission("read")
    return doc


class ProjectDocument(Document):
    def validate(self):
        frappe.get_doc("Project", self.project).check_permission("write")
        previous = self.get_doc_before_save()
        if previous and previous.project != self.project:
            frappe.throw("The Project cannot be changed after creation.")
        self.clean_overrides()

    def clean_overrides(self):
        """Store only non-empty overrides of values that come from linked records."""
        blocked = {*stored_fieldnames(self), *NOT_OVERRIDABLE, "project", "overrides"}
        overrides = {}
        for key, value in parse_overrides(self.get("overrides")).items():
            if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]+", key) or key in blocked:
                frappe.throw(f"{key} cannot be overridden.")
            if text(value):
                overrides[key] = text(value)
        self.overrides = json.dumps(overrides, sort_keys=True) if overrides else None

    def on_trash(self):
        frappe.get_doc("Project", self.project).check_permission("write")

    def before_print(self, print_settings=None):
        # Never trust client-supplied resolved values in standard print requests.
        self.print_context = resolve_print_context(self)


def resolve_print_context(doc):
    from wahni_solar.solar_project.sources import resolve_context

    category = category_for(doc.doctype)
    frappe.get_doc("Project", doc.project).check_permission("read")
    context = resolve_context(doc.project, categories=(category,), include_sources=False)
    values = form_values(context)[category]
    stored_fields = stored_fieldnames(doc)
    for fieldname in stored_fields:
        values[fieldname] = text(doc.get(fieldname))
    date = doc.get("agreement_date")
    if category == "KSEB Agreement":
        values["agreement_date"] = str(getdate(date).day) if date else ""
        values["date_month_year"] = getdate(date).strftime("%B %Y") if date else ""
    elif category == "Customer Vendor Agreement":
        values["date"] = getdate(date).strftime("%d-%m-%Y") if date else ""
    if category == "Check List":
        values["inverter_make_and_serial_number"] = "\n".join(filter(None, (
            values.get("inverter_make_and_serial_number"), values.get("inverter_serial_numbers"))))
        values["plant_individual_capacity"] = panel_watt_peak(context)
        values["inverter_capacity"] = text((context.get("inverter") or {}).get("custom_rated_capacity"))
    if category in ("Check List", "Project Completion Report"):
        key = "voltage_and_number_of_phase" if category == "Check List" else "voltage_and_supply_system"
        values[key] = ", ".join(filter(None, (values.get("supply_voltage"), values.get(key))))
    defaults = {key: value for key, value in values.items() if key not in stored_fields and key not in NOT_OVERRIDABLE}
    overrides = {key: text(value) for key, value in parse_overrides(doc.get("overrides")).items()
                 if key not in stored_fields and key not in NOT_OVERRIDABLE and text(value)}
    values.update(overrides)
    missing = [key for key, value in values.items() if not value]
    # Material Items are only read to identify panel/inverter equipment; list the main records.
    sources = [ref for ref in context["permissions"] if ref["doctype"] != "Item"]
    return {"values": values, "warnings": context["warnings"], "missing_fields": missing,
            "sources": sources, "stored_fields": stored_fields, "defaults": defaults, "overrides": overrides}


def render_document(doc):
    doc.check_permission("read")
    doc.check_permission("print")
    category = category_for(doc.doctype)
    # get_print calls before_print with this same Document. Its resolved context
    # therefore describes exactly the values used in the generated PDF.
    content = frappe.get_print(doc.doctype, doc.name, print_format=PRINT_FORMATS[category],
                               doc=doc, as_pdf=True, no_letterhead=1)
    return content, doc.print_context


@frappe.whitelist(methods=["POST"])
def open_project_document(project, category):
    if category not in DOCUMENT_TYPES:
        frappe.throw("Choose a supported Project document.")
    doc = ensure_documents(project, (category,))[category]
    return {"doctype": doc.doctype, "name": doc.name}


@frappe.whitelist()
def get_document_preview(doctype, name):
    category_for(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    return resolve_print_context(doc)


def has_document_permission(doc, ptype=None, user=None, **kwargs):
    # Frappe checks create permission before a Project has been selected. The
    # controller enforces Project write permission on insertion and every save.
    if ptype == "create" and not doc.get("project"):
        return True
    permission = "write" if ptype in ("create", "write", "delete") else "read"
    if ptype == "share":
        return False
    return bool(doc.get("project") and frappe.has_permission("Project", permission, doc.project, user=user))


def document_query_conditions(doctype, user=None):
    category_for(doctype)
    projects = frappe.get_list("Project", pluck="name", limit_page_length=0, user=user or frappe.session.user)
    if not projects:
        return "1=0"
    names = ", ".join(frappe.db.escape(name) for name in projects)
    return f"`tab{doctype}`.`project` IN ({names})"


def customer_vendor_agreement_query(user=None):
    return document_query_conditions('Customer Vendor Agreement', user)


def customer_kseb_agreement_query(user=None):
    return document_query_conditions('Customer KSEB Agreement', user)


def solar_installation_checklist_query(user=None):
    return document_query_conditions('Solar Installation Checklist', user)


def solar_completion_certificate_query(user=None):
    return document_query_conditions('Solar Completion Certificate', user)
