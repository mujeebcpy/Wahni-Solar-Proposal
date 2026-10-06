"""Stored document-specific inputs and permission-aware, live print context."""

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from wahni_solar.solar_project.documents import form_values, text


DOCUMENT_TYPES = {
    "Customer Vendor Agreement": "Customer Vendor Agreement",
    "KSEB Agreement": "Customer KSEB Agreement",
    "Check List": "Solar Installation Checklist",
    "Project Completion Report": "Solar Completion Certificate",
}
PRINT_FORMATS = {category: doctype for category, doctype in DOCUMENT_TYPES.items()}


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


class ProjectDocument(Document):
    def validate(self):
        frappe.get_doc("Project", self.project).check_permission("write")
        previous = self.get_doc_before_save()
        if previous and previous.project != self.project:
            frappe.throw("The Project cannot be changed after creation.")

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
    stored_fields = []
    for field in doc.meta.fields:
        if field.fieldtype in ("Section Break", "Column Break", "HTML", "Tab Break") or field.fieldname == "project":
            continue
        stored_fields.append(field.fieldname)
        values[field.fieldname] = text(doc.get(field.fieldname))
    date = doc.get("agreement_date")
    if category == "KSEB Agreement":
        values["agreement_date"] = str(getdate(date).day) if date else ""
        values["date_month_year"] = getdate(date).strftime("%B %Y") if date else ""
    elif category == "Customer Vendor Agreement":
        values["date"] = getdate(date).strftime("%d-%m-%Y") if date else ""
    if category == "Check List":
        values["inverter_make_and_serial_number"] = "\n".join(filter(None, (
            values.get("inverter_make_and_serial_number"), values.get("inverter_serial_numbers"))))
        panel = context.get("panel") or {}
        values["plant_individual_capacity"] = text(panel.get("custom_panel_watt_peak"))
        if values["plant_individual_capacity"]:
            values["plant_individual_capacity"] += " Wp"
        values["inverter_capacity"] = text((context.get("inverter") or {}).get("custom_rated_capacity"))
    if category in ("Check List", "Project Completion Report"):
        key = "voltage_and_number_of_phase" if category == "Check List" else "voltage_and_supply_system"
        values[key] = ", ".join(filter(None, (values.get("supply_voltage"), values.get(key))))
    missing = [key for key, value in values.items() if not value]
    return {"values": values, "warnings": context["warnings"], "missing_fields": missing,
            "sources": context["permissions"], "stored_fields": stored_fields}


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
