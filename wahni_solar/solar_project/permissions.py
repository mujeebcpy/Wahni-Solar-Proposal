import frappe

from wahni_solar.solar_project.constants import ACTIVE_STATUSES


def has_report_permission(doc, ptype=None, user=None, **kwargs):
    if ptype == "delete":
        if doc.status in ACTIVE_STATUSES:
            return False
        user = user or frappe.session.user
        if user == "Administrator":
            return True
        if not {"System Manager", "Projects Manager"}.intersection(frappe.get_roles(user)):
            return False
        return bool(doc.project and frappe.has_permission("Project", "read", doc.project, user=user))
    if ptype not in (None, "read", "select", "print", "export", "email", "report"):
        return False
    return bool(doc.project and frappe.has_permission("Project", "read", doc.project, user=user))


def report_query_conditions(user=None):
    projects = frappe.get_list("Project", pluck="name", limit_page_length=0, user=user or frappe.session.user)
    if not projects:
        return "1=0"
    names = ", ".join(frappe.db.escape(name) for name in projects)
    return f"`tabProject Report`.`project` IN ({names})"
