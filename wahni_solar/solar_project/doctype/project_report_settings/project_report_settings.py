import frappe
from frappe.model.document import Document


class ProjectReportSettings(Document):
    def validate(self):
        if self.invoice_print_format and frappe.db.get_value(
            "Print Format", self.invoice_print_format, "doc_type"
        ) != "Sales Invoice":
            frappe.throw("Choose a Sales Invoice print format.")
