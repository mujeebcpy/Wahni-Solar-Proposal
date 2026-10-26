import frappe
from frappe.model.document import Document

from wahni_solar.solar_project.constants import ACTIVE_STATUSES


class ProjectReport(Document):
    def onload(self):
        from wahni_solar.solar_project.api import available_outputs

        self.set_onload("downloads", available_outputs(self))

    def after_delete(self):
        from wahni_solar.solar_project.api import clear_outputs

        clear_outputs(self.name)

    def on_trash(self):
        # Administrator bypasses normal permission checks, so enforce this here too.
        if self.status in ACTIVE_STATUSES:
            frappe.throw("Wait until report generation has finished before deleting this report.")
        if not self.project:
            return
        # Each Project has one report; clear its link before Frappe's linked-document check.
        # Keep this in the delete transaction so a failed deletion rolls it back.
        if frappe.db.get_value("Project", self.project, "custom_latest_project_report") == self.name:
            frappe.db.set_value("Project", self.project,
                                {"custom_latest_project_report": None, "custom_project_report_status": None},
                                update_modified=False)
