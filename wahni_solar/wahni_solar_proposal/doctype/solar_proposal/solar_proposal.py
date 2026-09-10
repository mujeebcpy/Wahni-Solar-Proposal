# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.model.mapper import get_mapped_doc
from erpnext.crm.doctype.lead.lead import _make_customer


class SolarProposal(Document):
	def autoname(self):
		today = frappe.utils.getdate()
		if today.month >= 4:
			fy_start = today.year % 100
			fy_end = (today.year + 1) % 100
		else:
			fy_start = (today.year - 1) % 100
			fy_end = today.year % 100
		fy = f"{fy_start:02d}-{fy_end:02d}"
		self.name = make_autoname(f"WGT-SQ-{fy}-.###")

@frappe.whitelist()
def make_solar_proposal(source_name, target_doc=None):
    def set_missing_values(source, target):
        target.proposal_date = frappe.utils.today()

    doclist = get_mapped_doc("Lead", source_name, {
        "Lead": {
            "doctype": "Solar Proposal",
            "field_map": {
                "name": "lead"
            }
        }
    }, target_doc, set_missing_values)

    return doclist

@frappe.whitelist()
def make_project(source_name, target_doc=None):
    lead = frappe.db.get_value("Solar Proposal", source_name, "lead")

    if not lead:
        frappe.throw("Solar Proposal {0} has no Lead linked".format(source_name))

    # reuse existing customer if this Lead was already converted
    customer = frappe.db.get_value("Customer", {"lead_name": lead})

    if not customer:
        customer_doc = _make_customer(lead, ignore_permissions=True)
        customer_doc.insert(ignore_permissions=True)
        customer = customer_doc.name
        frappe.db.set_value("Lead", lead, "status", "Converted")

    def set_missing_values(source, target):
        target.customer = customer
        target.project_name = f"{source.package_name} - {customer}"
        target.custom_solar_proposal = source.name

    doclist = get_mapped_doc("Solar Proposal", source_name, {
        "Solar Proposal": {
            "doctype": "Project",
            "field_map": {"name": "custom_solar_proposal"}
        },
        "Solar Proposal BOM Item": {
            "doctype": "Solar Proposal BOM Item"
        },
        "Project Cost Breakdown": {
            "doctype": "Project Cost Breakdown"
        }
    }, target_doc, set_missing_values)

    return doclist
