import frappe


def execute():
    """Move the old Solar Proposal `lead` link into proposal_to/party/customer_name."""
    # Frappe keeps the dropped column after model sync, so the old values are still readable.
    if not frappe.db.has_column("Solar Proposal", "lead"):
        return

    proposals = frappe.db.sql(
        """
        select name, lead from `tabSolar Proposal`
        where ifnull(lead, '') != '' and ifnull(party, '') = ''
        """,
        as_dict=True,
    )

    for proposal in proposals:
        lead_name, company_name = frappe.db.get_value(
            "Lead", proposal.lead, ["lead_name", "company_name"]
        ) or (None, None)
        frappe.db.set_value(
            "Solar Proposal",
            proposal.name,
            {
                "proposal_to": "Lead",
                "party": proposal.lead,
                "customer_name": company_name or lead_name,
            },
            update_modified=False,
        )
