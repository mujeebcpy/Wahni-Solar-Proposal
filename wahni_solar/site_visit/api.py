"""Proposal visit snapshots and the optional Project dependency."""

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_default_address
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.utils import cint

SUPERVISOR_ROLE = "Project Supervisor"
DRAWING_FIELDS = ("building_outline", "panel_layout", "db_layout")


def get_proposal_visit(proposal):
    if not proposal:
        return None
    return frappe.db.get_value(
        "Site Visit", {"solar_proposal": proposal}, ["name", "status", "solar_proposal"], as_dict=True
    )


def proposal_defaults(proposal):
    """Read the party only after checking access to its source proposal."""
    proposal.check_permission("read")
    party = frappe.get_doc(proposal.proposal_to, proposal.party)
    values = {
        "solar_proposal": proposal.name,
        "company": proposal.company,
        "currency": proposal.currency or frappe.defaults.get_global_default("currency"),
        "customer_name": proposal.customer_name,
        "requested_capacity_kw": proposal.capacity_kw,
        "contact_number": party.get("mobile_no") or party.get("phone"),
        "email_id": party.get("email_id"),
    }
    lead = None
    if proposal.proposal_to == "Lead":
        lead = party
        values["customer"] = frappe.db.get_value("Customer", {"lead_name": party.name}, "name")
    elif proposal.proposal_to == "Customer":
        values["customer"] = party.name
        if party.get("lead_name"):
            lead = frappe.get_doc("Lead", party.lead_name)
    if lead:
        values.update({
            "lead": lead.name,
            "lead_owner": lead.get("lead_owner"),
            "lead_source": lead.get("source"),
            "consumer_number": lead.get("custom_kseb_consumer_no"),
            "consumer_phone_number": lead.get("custom_kseb_connected_mobile_no"),
        })
        values["contact_number"] = values["contact_number"] or lead.get("mobile_no") or lead.get("phone")
        values["email_id"] = values["email_id"] or lead.get("email_id")

    contact_name = party.get("customer_primary_contact") or get_default_contact(party.doctype, party.name)
    if not contact_name and lead and lead.name != party.name:
        contact_name = get_default_contact("Lead", lead.name)
    if contact_name:
        contact = frappe.get_doc("Contact", contact_name)
        values["contact_number"] = values["contact_number"] or contact.get("mobile_no") or contact.get("phone")
        values["email_id"] = values["email_id"] or contact.get("email_id")
    address_name = party.get("customer_primary_address") or get_default_address(party.doctype, party.name)
    if not address_name and lead and lead.name != party.name:
        address_name = get_default_address("Lead", lead.name)
    if address_name:
        address = frappe.get_doc("Address", address_name)
        values.update({
            "address": "\n".join(address.get(key) for key in
                                 ("address_line1", "address_line2", "city", "state", "country", "pincode")
                                 if address.get(key)),
            "location": address.get("city"),
            "pincode": address.get("pincode"),
        })
    return values


@frappe.whitelist()
def make_site_visit(source_name):
    """Open the existing report, or return an unsaved snapshot (never insert here)."""
    proposal = frappe.get_doc("Solar Proposal", source_name)
    proposal.check_permission("read")
    existing = get_proposal_visit(source_name)
    if existing:
        visit = frappe.get_doc("Site Visit", existing.name)
        visit.check_permission("read")
        return visit
    visit = frappe.new_doc("Site Visit")
    visit.check_permission("create")
    visit.update(proposal_defaults(proposal))
    return visit


def is_eligible_supervisor(employee):
    user = frappe.db.get_value("Employee", {"name": employee, "status": "Active"}, "user_id")
    return bool(
        user
        and frappe.db.get_value("User", user, "enabled")
        and not frappe.db.get_value("Role", SUPERVISOR_ROLE, "disabled")
        and SUPERVISOR_ROLE in frappe.get_roles(user)
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def supervisor_query(doctype, txt, searchfield, start, page_len, filters):
    # Expose only eligible names, not Employee records or HR data. Sales staff do
    # not need broad Employee read permissions merely to schedule a visit.
    if not frappe.has_permission("Site Visit", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if frappe.db.get_value("Role", SUPERVISOR_ROLE, "disabled"):
        return []
    employee = frappe.qb.DocType("Employee")
    user = frappe.qb.DocType("User")
    role = frappe.qb.DocType("Has Role")
    return (
        frappe.qb.from_(employee)
        .join(user).on(user.name == employee.user_id)
        .join(role).on((role.parent == user.name) & (role.parenttype == "User") & (role.parentfield == "roles"))
        .select(employee.name, employee.employee_name)
        .where((employee.status == "Active") & (user.enabled == 1) & (role.role == SUPERVISOR_ROLE))
        .where(employee.name.like(f"%{txt}%") | employee.employee_name.like(f"%{txt}%"))
        .orderby(employee.employee_name)
        .offset(max(0, cint(start)))
        .limit(min(100, max(1, cint(page_len))))
        .run()
    )


def warn_incomplete_visit(visit):
    if not visit or visit.status != "Completed":
        frappe.msgprint(
            _("Site Visit is missing or not completed for this Solar Proposal. You can continue creating the Project."),
            title=_("Site Visit Pending"), indicator="orange",
        )


def validate_project_site_visit(doc, method=None):
    proposal = doc.get("custom_solar_proposal")
    selected = doc.get("custom_site_visit")
    if not proposal and not selected:
        return
    if selected:
        visit = frappe.db.get_value(
            "Site Visit", selected, ["name", "status", "solar_proposal"], as_dict=True
        )
        if not visit or visit.solar_proposal != proposal:
            frappe.throw(_("Site Visit must belong to the Project's Solar Proposal."))
    else:
        visit = get_proposal_visit(proposal)
        if visit:
            doc.custom_site_visit = visit.name
    previous = doc.get_doc_before_save()
    if (
        not previous
        or previous.get("custom_solar_proposal") != proposal
        or previous.get("custom_site_visit") != doc.get("custom_site_visit")
    ):
        warn_incomplete_visit(visit)
