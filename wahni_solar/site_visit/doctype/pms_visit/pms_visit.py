"""Preventive maintenance reports, including project-less historical imports."""

import frappe
from frappe import _
from frappe.model.document import Document

from wahni_solar.field_portal.access import COMPLETION_ROLES, enforce_assignment
from wahni_solar.site_visit.api import SUPERVISOR_ROLE, is_eligible_supervisor

COMPLETION_FIELDS = {
    "pms_date": "PMS Date",
    "place": "Place",
    "plant_capacity_kw": "Plant Capacity (kW)",
    "site_location_link": "Site Location Link",
    "ac_db_string_inverter": "AC DB and String Inverter",
    "panel_image": "Panel Image",
    "house_image": "House Image",
    "inspection_remarks": "Inspection Remarks",
}


def missing_completion_fields(doc):
    return [label for field, label in COMPLETION_FIELDS.items() if not str(doc.get(field) or "").strip()]


def project_values(project):
    project = frappe.get_doc("Project", project)
    project.check_permission("select")
    if project.status != "Completed":
        frappe.throw(_("PMS visits can only be created for completed Projects."))
    return {
        "customer": project.customer or None,
        "client_name": frappe.db.get_value("Customer", project.customer, "customer_name") if project.customer else None,
    }


@frappe.whitelist()
def get_project_values(project):
    if not frappe.has_permission("PMS Visit", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return project_values(project)


class PMSVisit(Document):
    def validate(self):
        previous = self.get_doc_before_save()
        enforce_assignment(self, previous)
        if self.status not in ("Assigned", "In Progress", "Completed"):
            frappe.throw(_("Choose a valid PMS Visit status."))
        completing = self.status == "Completed" and (not previous or previous.status != "Completed")
        if completing:
            frappe.only_for(COMPLETION_ROLES)
        if self.status == "Completed":
            missing = missing_completion_fields(self)
            if missing:
                frappe.throw(_("Complete the following fields before completing the PMS Visit: {0}").format(
                    ", ".join(_(label) for label in missing)
                ))
        legacy = self.get("legacy_site_data_collection")
        if previous and legacy != previous.get("legacy_site_data_collection"):
            frappe.throw(_("The legacy report reference cannot be changed."))
        if not previous and legacy:
            frappe.throw(_("New PMS visits cannot have a legacy report reference."))
        # Keep already copied UAT reports editable; no new legacy copies are allowed.
        historical = bool(legacy and previous and not previous.project)
        if not self.project and not historical:
            frappe.throw(_("Project is required for new PMS visits."))
        # Existing maintenance history remains editable if its Project is later
        # reopened. A new report or a changed Project must be completed now.
        if self.project and (not previous or previous.project != self.project):
            values = project_values(self.project)
            # Project selection suggests a Customer, but explicit Customer or
            # free-text client choices must also work for customer-less Projects.
            if not self.customer and not (self.client_name or "").strip():
                self.update(values)
        if not self.customer and not (self.client_name or "").strip():
            frappe.throw(_("Select a Customer or enter a Client Name."))

        if self.get("service_person"):
            changed = not previous or previous.get("service_person") != self.service_person
            if (changed or completing) and not is_eligible_supervisor(self.service_person):
                frappe.throw(_("Service Person Name must be an active Employee whose enabled User has the Project Supervisor role."))
            self.service_person_name = (
                frappe.db.get_value("Employee", self.service_person, "employee_name")
                if changed else previous.service_person_name
            )
        else:
            historical_person = previous and not previous.get("service_person") and previous.get("service_person_name")
            if not historical_person or not (self.service_person_name or "").strip():
                frappe.throw(_("Select an Employee as Service Person Name."))
