from frappe import _


def get_data():
    return {
        "fieldname": "solar_proposal",
        "non_standard_fieldnames": {"Project": "custom_solar_proposal"},
        "transactions": [{"label": _("Solar"), "items": ["Site Visit", "Project"]}],
    }
