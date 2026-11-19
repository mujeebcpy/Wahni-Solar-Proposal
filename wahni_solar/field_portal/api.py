"""Session and login endpoints for the Wahni Field PWA (/field)."""

import frappe
from frappe import _

from wahni_solar.field_portal.access import field_access_problem, get_employee, is_office

# No trailing slash: Frappe's nginx config rewrites "/field/" to "/field".
FIELD_ROUTE = "/field"


@frappe.whitelist(methods=["GET"])
def get_session_info():
    """Identity and portal eligibility of the session user, resolved on the server."""
    user = frappe.session.user
    if user == "Guest":
        raise frappe.AuthenticationError(_("Please log in to use Wahni Field."))
    info = frappe.db.get_value("User", user, ["name", "full_name", "user_image"], as_dict=True)
    problem = field_access_problem(user)
    info.update({"allowed": not problem, "reason": problem, "is_office": is_office(user), "employee": None})
    employee = get_employee(user)
    if employee:
        info["employee"] = frappe.db.get_value(
            "Employee", employee,
            ["name", "employee_name", "designation", "department", "company", "image", "cell_number"],
            as_dict=True,
        )
    return info


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_login_options():
    """Login methods configured for this site; social logins return to /field."""
    from frappe.utils.oauth import get_oauth2_authorize_url, get_oauth_keys
    from frappe.utils.password import get_decrypted_password

    providers = []
    for provider in frappe.get_all(
        "Social Login Key", filters={"enable_social_login": 1},
        fields=["name", "client_id", "base_url", "provider_name"], order_by="name",
    ):
        if not (provider.client_id and provider.base_url and get_oauth_keys(provider.name)):
            continue
        if not get_decrypted_password("Social Login Key", provider.name, "client_secret", raise_exception=False):
            continue
        providers.append({
            "name": provider.name,
            "label": provider.provider_name,
            "auth_url": get_oauth2_authorize_url(provider.name, FIELD_ROUTE),
        })
    return {
        "password_login": not frappe.get_system_settings("disable_user_pass_login"),
        "providers": providers,
    }


def get_boot():
    from frappe.boot import load_translations

    boot = frappe._dict(site_name=frappe.local.site, lang=frappe.local.lang, field_route=FIELD_ROUTE)
    load_translations(boot)
    return boot


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_boot_for_dev():
    """Boot data for the Vite dev server, which cannot render field.html."""
    if not frappe.conf.developer_mode:
        frappe.throw(_("This method is only meant for developer mode"))
    return get_boot()


@frappe.whitelist(methods=["GET"])
def get_csrf_token():
    """Fresh CSRF token after an in-app login, so unsaved forms survive re-login."""
    token = frappe.sessions.get_csrf_token()
    frappe.db.commit()  # GET requests are not committed automatically
    return token


@frappe.whitelist(methods=["GET"])
def get_home_summary():
    """Open work counts and recent items for the session employee only."""
    from wahni_solar.field_portal.access import ASSIGNEE_FIELDS, require_field_user

    employee = require_field_user()
    summary = {"counts": {}, "recent": []}
    for doctype, title_field in (("Site Visit", "customer_name"), ("PMS Visit", "client_name")):
        filters = {ASSIGNEE_FIELDS[doctype]: employee, "status": ["in", ["Assigned", "In Progress"]]}
        summary["counts"][doctype] = frappe.db.count(doctype, filters) if frappe.has_permission(doctype, "read") else 0
        for row in frappe.get_list(doctype, filters=filters, fields=["name", "status", title_field, "modified"],
                                   order_by="modified desc", limit_page_length=5):
            summary["recent"].append({"doctype": doctype, "name": row.name, "status": row.status,
                                      "title": row.get(title_field) or row.name, "modified": row.modified})
    if "hrms" in frappe.get_installed_apps():
        summary["counts"]["Expense Claim"] = len(frappe.get_list(
            "Expense Claim", filters={"employee": employee, "docstatus": 0}, pluck="name", limit_page_length=0))
    summary["recent"] = sorted(summary["recent"], key=lambda row: row["modified"], reverse=True)[:5]
    return summary
