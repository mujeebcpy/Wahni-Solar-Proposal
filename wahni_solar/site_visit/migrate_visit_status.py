"""Preserve visit history when introducing the assignment lifecycle."""

import frappe

from wahni_solar.site_visit.doctype.pms_visit.pms_visit import (
    COMPLETION_FIELDS,
    missing_completion_fields,
)


def execute():
    frappe.db.set_value("Site Visit", {"status": "Draft"}, "status", "Assigned", update_modified=False)

    # The new column defaults to Assigned. Previously saved PMS reports that
    # already contain all inspection details are completed history, not new work.
    for visit in frappe.get_all(
        "PMS Visit",
        fields=["name", "status", *COMPLETION_FIELDS],
    ):
        if visit.status not in (None, "", "Assigned"):
            continue
        status = "Assigned" if missing_completion_fields(visit) else "Completed"
        if visit.status != status:
            frappe.db.set_value("PMS Visit", visit.name, "status", status, update_modified=False)
