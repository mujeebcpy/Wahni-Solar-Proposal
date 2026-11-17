"""One editable, proposal-linked site survey report."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from wahni_solar.field_portal.access import COMPLETION_ROLES, enforce_assignment
from wahni_solar.site_visit.api import (
    DRAWING_FIELDS,
    SUPERVISOR_ROLE,
    is_eligible_supervisor,
    proposal_snapshot,
)


class SiteVisit(Document):
    def before_validate(self):
        if self.is_new() and self.solar_proposal:
            for field, value in proposal_snapshot(self.solar_proposal).items():
                if not self.get(field):
                    self.set(field, value)

    def validate(self):
        previous = self.get_doc_before_save()
        enforce_assignment(self, previous)
        if previous and previous.solar_proposal != self.solar_proposal:
            frappe.throw(_("The Solar Proposal cannot be changed on an existing Site Visit."))
        if self.status not in ("Assigned", "In Progress", "Completed"):
            frappe.throw(_("Choose a valid Site Visit status."))
        completing = self.status == "Completed" and (not previous or previous.status != "Completed")
        if completing:
            frappe.only_for(COMPLETION_ROLES)
        if self.status == "Completed":
            if not self.visit_date or not self.site_visit_by:
                frappe.throw(_("Visit Date and Site Visit By are required to complete the Site Visit."))
        if not previous and not self.site_visit_by:
            frappe.throw(_("Select an Employee in Site Visit By to assign the Site Visit."))
        # Do not invalidate a historical assignment when an employee leaves.
        if self.site_visit_by and (not previous or previous.site_visit_by != self.site_visit_by or completing):
            if not is_eligible_supervisor(self.site_visit_by):
                frappe.throw(_("Site Visit By must be an active Employee whose enabled User has the Project Supervisor role."))
        if not 0 <= flt(self.loan_percentage) <= 100:
            frappe.throw(_("Loan Percentage must be between 0 and 100."))
        for field in DRAWING_FIELDS:
            url = self.get(field)
            if url and (not previous or previous.get(field) != url):
                file_name = frappe.db.get_value("File", {"file_url": url, "is_private": 1}, "name")
                if not file_name:
                    frappe.throw(_("Layout drawings must be uploaded as private files."))
                frappe.get_doc("File", file_name).check_permission("read")
