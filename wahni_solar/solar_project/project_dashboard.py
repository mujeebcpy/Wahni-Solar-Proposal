from frappe import _


def get_dashboard_data(data):
    data.setdefault("transactions", []).append({
        "label": _("Solar"),
        "items": ["Project Report", "KSEB Grid Check", "Solar Proposal"],
    })
    data.setdefault("non_standard_fieldnames", {})["Project Report"] = "project"
    data.setdefault("internal_links", {}).update({
        "Solar Proposal": "custom_solar_proposal",
        "KSEB Grid Check": "custom_report_grid_check",
    })
    return data
