from frappe import _


def get_dashboard_data(data):
    data.setdefault("transactions", []).append({
        "label": _("Solar"),
        "items": ["Solar Proposal", "KSEB Grid Check"]
    })

    data.setdefault("non_standard_fieldnames", {}).update({
        "Solar Proposal": "lead"
    })

    return data