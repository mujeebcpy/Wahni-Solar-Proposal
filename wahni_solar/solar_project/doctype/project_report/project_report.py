import frappe
from frappe.model.document import Document

from wahni_solar.solar_project.constants import ACTIVE_STATUSES


class ProjectReport(Document):
    def on_trash(self):
        # Administrator bypasses normal permission checks, so enforce this here too.
        if self.status in ACTIVE_STATUSES:
            frappe.throw("Wait until report generation has finished before deleting this report.")
        if not self.project:
            return
        # Generation also locks Project. Do not wait while deletion holds a report
        # lock: a concurrent generation may be trying to update that same report.
        latest = frappe.db.get_value(
            "Project", self.project, "custom_latest_project_report", for_update=True, wait=False
        )
        if latest != self.name:
            return
        remaining = frappe.get_all(
            "Project Report",
            filters={"project": self.project, "name": ["!=", self.name]},
            fields=["name", "status"],
            order_by="creation desc, name desc",
            limit_page_length=1,
        )
        replacement = remaining[0] if remaining else {}
        # Clear the incoming link before Frappe's standard linked-document check.
        # Keep this in the delete transaction so a failed deletion rolls it back.
        frappe.db.set_value(
            "Project", self.project,
            {"custom_latest_project_report": replacement.get("name"),
             "custom_project_report_status": replacement.get("status")},
            update_modified=False,
        )
