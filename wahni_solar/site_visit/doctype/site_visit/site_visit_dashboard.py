from frappe import _


def get_data():
    return {
        "fieldname": "custom_site_visit",
        "transactions": [{"label": _("Projects"), "items": ["Project"]}],
    }
