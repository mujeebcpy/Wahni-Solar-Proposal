"""Preventive maintenance reports, including project-less historical imports."""

import frappe
from frappe import _
from frappe.model.document import Document

from wahni_solar.site_visit.api import is_eligible_supervisor


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
        legacy = self.get("legacy_site_data_collection")
        importing = bool(frappe.flags.get("in_legacy_pms_import"))
        if previous and legacy != previous.get("legacy_site_data_collection"):
            frappe.throw(_("The legacy report reference cannot be changed."))
        if not previous and legacy and not importing:
            frappe.throw(_("Legacy PMS reports can only be created by the migration command."))
        historical = bool(legacy and (
            (importing and not previous)
            or (previous and previous.get("legacy_site_data_collection") and not previous.project)
        ))
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
            if changed and not is_eligible_supervisor(self.service_person):
                frappe.throw(_("Service Person Name must be an active Employee whose enabled User has the Project Supervisor role."))
            self.service_person_name = (
                frappe.db.get_value("Employee", self.service_person, "employee_name")
                if changed else previous.service_person_name
            )
        else:
            historical_person = (
                (legacy and importing and not previous)
                or (previous and not previous.get("service_person") and previous.get("service_person_name"))
            )
            if not historical_person or not (self.service_person_name or "").strip():
                frappe.throw(_("Select an Employee as Service Person Name."))
