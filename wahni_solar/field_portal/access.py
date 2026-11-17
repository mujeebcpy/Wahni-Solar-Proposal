"""Who may use the field portal, and which visits a field supervisor may touch.

Policy (agreed 2026-11-17):
- Office roles (System Manager, Projects Manager) see every visit, may assign or
  reassign it to anyone and are the only users who may edit/reopen a Completed visit.
- A *restricted supervisor* holds Project Supervisor without an office role. They
  see only visits assigned to their own active Employee, everywhere (Desk, REST,
  file URLs and /field), may create visits only for themselves and cannot reassign.
- Assignment truth is the employee Link (Site Visit By / Service Person), never
  the document owner.
"""

import frappe
from frappe import _

SUPERVISOR_ROLE = "Project Supervisor"
OFFICE_ROLES = frozenset(("System Manager", "Projects Manager"))
# Who may mark a visit Completed (assignee eligibility is still checked).
COMPLETION_ROLES = ("System Manager", "Projects Manager", SUPERVISOR_ROLE)
ASSIGNEE_FIELDS = {"Site Visit": "site_visit_by", "PMS Visit": "service_person"}


def is_office(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(OFFICE_ROLES.intersection(frappe.get_roles(user)))


def is_restricted(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return False
    roles = frappe.get_roles(user)
    return SUPERVISOR_ROLE in roles and not OFFICE_ROLES.intersection(roles)


def get_employee(user=None):
    """The session user's active Employee, resolved on the server only."""
    user = user or frappe.session.user
    if user in ("Guest", "Administrator"):
        return None
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def enforce_assignment(doc, previous):
    """Self-assign new visits and block reassignment for restricted supervisors."""
    if doc.flags.ignore_permissions:
        return
    field = ASSIGNEE_FIELDS[doc.doctype]
    if previous and previous.get("status") == "Completed" and not is_office():
        frappe.throw(_("Completed visits can only be changed or reopened by the office."), frappe.PermissionError)
    if not is_restricted():
        return
    employee = get_employee()
    if not employee:
        frappe.throw(_("Your user is not linked to an active Employee."), frappe.PermissionError)
    if not previous:
        if not doc.get(field):
            doc.set(field, employee)
        elif doc.get(field) != employee:
            frappe.throw(_("You can only create visits assigned to yourself."), frappe.PermissionError)
        return
    if previous.get(field) != doc.get(field):
        frappe.throw(_("Only the office can reassign a visit."), frappe.PermissionError)
    if doc.doctype == "PMS Visit" and previous.get("project") != doc.get("project"):
        frappe.throw(_("Only the office can change the Project of a PMS Visit."), frappe.PermissionError)


def visit_has_permission(doc, ptype=None, user=None, **kwargs):
    """Document-level guard for Site Visit and PMS Visit (Desk, REST, files).

    Uses the stored assignee/status so an unsaved edit cannot grant itself access.
    Must return True explicitly: Frappe treats a falsy hook result as denial.
    """
    user = user or frappe.session.user
    if is_office(user):
        return True
    name = doc.get("name") if not doc.get("__islocal") else None
    stored = name and frappe.db.get_value(
        doc.doctype, name, [ASSIGNEE_FIELDS[doc.doctype], "status"], as_dict=True
    )
    if not stored:
        # New records: the controller self-assigns and validates (enforce_assignment).
        return True
    if is_restricted(user):
        employee = get_employee(user)
        if not employee or stored.get(ASSIGNEE_FIELDS[doc.doctype]) != employee:
            return False
    if ptype in ("write", "delete", "cancel", "submit", "amend") and stored.status == "Completed":
        return False
    return True


def _assignee_condition(doctype, user=None):
    user = user or frappe.session.user
    if not is_restricted(user):
        return ""
    employee = get_employee(user)
    if not employee:
        return "1=0"
    return f"`tab{doctype}`.`{ASSIGNEE_FIELDS[doctype]}` = {frappe.db.escape(employee)}"


def site_visit_query_conditions(user=None, **kwargs):
    return _assignee_condition("Site Visit", user)


def pms_visit_query_conditions(user=None, **kwargs):
    return _assignee_condition("PMS Visit", user)


def field_access_problem(user=None):
    """Why the user cannot use Wahni Field, or None when they can."""
    user = user or frappe.session.user
    if user == "Guest":
        return _("Please log in to use Wahni Field.")
    if SUPERVISOR_ROLE not in frappe.get_roles(user) or frappe.db.get_value("Role", SUPERVISOR_ROLE, "disabled"):
        return _("Wahni Field is available to Project Supervisors only.")
    if not get_employee(user):
        return _("Your user is not linked to an active Employee.")
    return None


def require_field_user():
    """Gate for every /field API: enabled user, active Employee, Project Supervisor role.

    Returns the Employee name. Office users must also be supervisors with an
    Employee to use the portal; they keep Desk for administration.
    """
    if frappe.session.user == "Guest":
        raise frappe.AuthenticationError(_("Please log in to use Wahni Field."))
    problem = field_access_problem()
    if problem:
        frappe.throw(problem, frappe.PermissionError)
    return get_employee()
