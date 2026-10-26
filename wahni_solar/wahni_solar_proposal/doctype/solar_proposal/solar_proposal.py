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
from wahni_solar.wahni_solar_proposal import configuration
from wahni_solar.wahni_solar_proposal.rules import RuleError

PARTY_TYPES = ("Customer", "Lead", "Prospect")


class SolarProposal(Document):
	def validate(self):
		if self.proposal_to not in PARTY_TYPES:
			frappe.throw(frappe._("Proposal To must be one of {0}").format(", ".join(PARTY_TYPES)))
		self.set_customer_name()
		previous = self.get_doc_before_save()
		if self.is_demo and (not previous or not previous.is_demo):
			frappe.only_for("System Manager")
		# The persisted version is authoritative; a request cannot bypass calculation
		# by labelling a new or current proposal as a legacy document.
		self.calculation_version = (
			configuration.VERSION if self.is_new() or self.flags.regenerate_configuration
			else (previous.calculation_version or "Legacy")
		)
		if self.calculation_version == "Legacy" and not self.flags.regenerate_configuration:
			return
		try:
			result = configuration.calculate(self, previous=previous,
				regenerate=bool(self.flags.regenerate_configuration),
				reprice=bool(self.flags.reprice_materials))
			configuration.apply_result(self, result)
		except RuleError as error:
			frappe.throw(str(error), title="Configuration rule error")

	@frappe.whitelist()
	def regenerate_materials(self):
		self.check_permission("write" if not self.is_new() else "create")
		self.flags.regenerate_configuration = True
		self.calculation_version = configuration.VERSION
		self.save()
		return self.as_dict()

	@frappe.whitelist()
	def refresh_valuation(self):
		self.check_permission("write" if not self.is_new() else "create")
		if self.calculation_version != configuration.VERSION:
			frappe.throw("Regenerate this legacy proposal before refreshing valuation.")
		self.flags.reprice_materials = True
		self.save()
		return self.as_dict()

	def before_print(self, print_settings=None):
		previous = frappe.get_doc(self.doctype, self.name) if not self.is_new() else None
		version = (previous.calculation_version or "Legacy") if previous else configuration.VERSION
		if version == configuration.VERSION:
			try:
				configuration.apply_result(self, configuration.calculate(self, previous=previous))
			except RuleError as error:
				frappe.throw(str(error), title="Configuration rule error")
			if self.costing_status != "Complete":
				frappe.throw("Resolve missing valuations or UOM conversions before printing this proposal.")

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
    proposal = frappe.get_doc("Solar Proposal", source_name)
    proposal.check_permission("read")
    proposal.before_print()
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
