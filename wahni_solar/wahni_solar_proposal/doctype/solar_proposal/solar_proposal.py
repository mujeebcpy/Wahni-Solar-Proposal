# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.model.mapper import get_mapped_doc
from erpnext.selling.doctype.quotation.quotation import (
    create_customer_from_lead,
    create_customer_from_prospect,
)

PARTY_TYPES = ("Customer", "Lead", "Prospect")


class SolarProposal(Document):
	def validate(self):
		if self.proposal_to not in PARTY_TYPES:
			frappe.throw(frappe._("Proposal To must be one of {0}").format(", ".join(PARTY_TYPES)))
		self.set_customer_name()

	def set_customer_name(self):
		if not self.party:
			return
		if self.proposal_to == "Customer":
			self.customer_name = frappe.db.get_value("Customer", self.party, "customer_name")
		elif self.proposal_to == "Lead":
			lead_name, company_name = frappe.db.get_value(
				"Lead", self.party, ["lead_name", "company_name"]
			)
			self.customer_name = company_name or lead_name
		elif self.proposal_to == "Prospect":
			self.customer_name = self.party

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

def _make_solar_proposal(party_type, source_name, target_doc=None):
    def set_missing_values(source, target):
        target.proposal_date = frappe.utils.today()
        target.proposal_to = party_type
        target.set_customer_name()

    return get_mapped_doc(party_type, source_name, {
        party_type: {
            "doctype": "Solar Proposal",
            "field_map": {
                "name": "party"
            }
        }
    }, target_doc, set_missing_values)


@frappe.whitelist()
def make_solar_proposal(source_name, target_doc=None):
    return _make_solar_proposal("Lead", source_name, target_doc)


@frappe.whitelist()
def make_solar_proposal_from_customer(source_name, target_doc=None):
    return _make_solar_proposal("Customer", source_name, target_doc)


def get_customer(proposal_to, party):
    """Return the Customer for a proposal party, converting a Lead/Prospect if needed."""
    if proposal_to == "Customer":
        return party

    if proposal_to == "Lead":
        customer = frappe.db.get_value("Customer", {"lead_name": party})
        if not customer:
            customer = create_customer_from_lead(party, ignore_permissions=True).name
            frappe.db.set_value("Lead", party, "status", "Converted")
        return customer

    if proposal_to == "Prospect":
        customer = frappe.db.get_value("Customer", {"prospect_name": party})
        return customer or create_customer_from_prospect(party, ignore_permissions=True).name

    frappe.throw("Proposal To must be one of {0}".format(", ".join(PARTY_TYPES)))


@frappe.whitelist()
def make_project(source_name, target_doc=None):
    proposal_to, party = frappe.db.get_value(
        "Solar Proposal", source_name, ["proposal_to", "party"]
    ) or (None, None)

    if not party:
        frappe.throw("Solar Proposal {0} has no Party linked".format(source_name))

    customer = get_customer(proposal_to, party)

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
