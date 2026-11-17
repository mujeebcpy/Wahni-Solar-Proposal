"""Expense Claims for the session employee (HRMS Expense Claim, normal permissions).

HRMS controllers keep totals, accounts, taxes, status and approval rules; this
API only scopes records to the session employee and limits editable fields.
"""

import frappe
from frappe import _
from frappe.model.workflow import get_transitions, get_workflow_name
from frappe.utils import cint, flt, nowdate
from frappe.utils import escape_html, strip_html_tags

from wahni_solar.field_portal.access import require_field_user
from wahni_solar.field_portal.utils import (
    attachments,
    ensure_not_stale,
    idempotent_insert,
    parse,
    remove_attachment,
)

DOCTYPE = "Expense Claim"
LIST_FIELDS = [
    "name", "posting_date", "status", "approval_status", "docstatus", "currency",
    "total_claimed_amount", "total_sanctioned_amount", "grand_total", "modified",
]
STATUS_FILTERS = {
    "draft": {"docstatus": 0},
    "approved": {"docstatus": 1, "approval_status": "Approved"},
    "rejected": {"approval_status": "Rejected"},
    "paid": {"docstatus": 1, "status": "Paid"},
    "unpaid": {"docstatus": 1, "status": ["in", ["Unpaid", "Partially Paid"]]},
}
ITEM_FIELDS = ("expense_date", "expense_type", "description", "amount", "project")


def require_expenses_enabled():
    if "hrms" not in frappe.get_installed_apps():
        frappe.throw(_("Expense claims need the HRMS app to be installed."))
    return require_field_user()


def own_claim(name, employee):
    doc = frappe.get_doc(DOCTYPE, name)
    # The portal shows only the employee's own claims, even to approvers.
    if doc.employee != employee:
        raise frappe.PermissionError(_("Not permitted"))
    doc.check_permission("read")
    return doc


def approvers(employee):
    """Approvers the employee may pick: their own, then their department's."""
    values = frappe.db.get_value("Employee", employee, ["expense_approver", "department"], as_dict=True)
    users = [values.expense_approver] if values.expense_approver else []
    if values.department:
        users += frappe.get_all(
            "Department Approver",
            filters={"parent": values.department, "parenttype": "Department", "parentfield": "expense_approvers"},
            pluck="approver", order_by="idx asc",
        )
    seen = []
    for user in users:
        if user and user not in seen and frappe.db.get_value("User", user, "enabled"):
            seen.append(user)
    return [{"value": user, "label": frappe.utils.get_fullname(user)} for user in seen]


def approver_required():
    return cint(frappe.db.get_single_value("HR Settings", "expense_approver_mandatory_in_expense_claim"))


@frappe.whitelist(methods=["GET"])
def get_form_options():
    employee = require_expenses_enabled()
    values = frappe.db.get_value(
        "Employee", employee, ["name", "employee_name", "company", "department"], as_dict=True
    )
    currency = frappe.get_cached_value("Company", values.company, "default_currency")
    types = frappe.get_list(
        "Expense Claim Type", fields=["name", "description"], order_by="name asc", limit_page_length=0
    )
    return {
        "employee": values,
        "currency": currency,
        "approvers": approvers(employee),
        "expense_types": types,
        "approver_required": approver_required(),
        "workflow": bool(get_workflow_name(DOCTYPE)),
    }


@frappe.whitelist(methods=["GET"])
def list_claims(status=None, start=0, page_length=20):
    employee = require_expenses_enabled()
    filters = {"employee": employee, **STATUS_FILTERS.get(status or "", {})}
    rows = frappe.get_list(
        DOCTYPE, filters=filters, fields=LIST_FIELDS, order_by="posting_date desc, creation desc",
        limit_start=max(0, cint(start)), limit_page_length=min(50, max(1, cint(page_length) or 20)),
    )
    names = [row.name for row in rows]
    types = {}
    if names:
        for item in frappe.get_all("Expense Claim Detail", filters={"parent": ["in", names]},
                                   fields=["parent", "expense_type"], order_by="idx asc"):
            types.setdefault(item.parent, [])
            if item.expense_type not in types[item.parent]:
                types[item.parent].append(item.expense_type)
    for row in rows:
        row.expense_types = types.get(row.name, [])
    return rows


def claim_payload(doc):
    actions = []
    if doc.docstatus == 0 and get_workflow_name(DOCTYPE):
        actions = [{"action": t.action, "next_state": t.next_state} for t in get_transitions(doc)]
    elif doc.docstatus == 0 and doc.has_permission("submit") and doc.approval_status in ("Approved", "Rejected"):
        actions = [{"action": "Submit", "next_state": None}]
    data = {
        field: doc.get(field)
        for field in (
            "name", "employee", "employee_name", "company", "currency", "posting_date", "expense_approver",
            "approval_status", "status", "docstatus", "project", "remark", "total_claimed_amount",
            "total_sanctioned_amount", "total_taxes_and_charges", "total_advance_amount", "grand_total",
            "total_amount_reimbursed", "modified", "workflow_state",
        )
    }
    data["expense_approver_name"] = frappe.utils.get_fullname(doc.expense_approver) if doc.expense_approver else None
    data["expenses"] = [
        {"name": row.name, "sanctioned_amount": row.sanctioned_amount, **{f: row.get(f) for f in ITEM_FIELDS}}
        for row in doc.expenses
    ]
    data["taxes"] = [{"description": row.description, "tax_amount": row.tax_amount} for row in doc.get("taxes", [])]
    data["advances"] = [
        {"employee_advance": row.employee_advance, "allocated_amount": row.allocated_amount}
        for row in doc.get("advances", []) if flt(row.allocated_amount)
    ]
    data["receipts"] = attachments(doc)
    data["editable"] = doc.docstatus == 0 and doc.has_permission("write")
    data["actions"] = actions
    return data


@frappe.whitelist(methods=["GET"])
def get_claim(name):
    return claim_payload(own_claim(name, require_expenses_enabled()))


def plain_text(value):
    return strip_html_tags(str(value or "")).strip()


def apply_values(doc, values, employee):
    allowed = {item["value"] for item in approvers(employee)}
    approver = values.get("expense_approver") or None
    if approver and approver not in allowed and approver != doc.get("expense_approver"):
        frappe.throw(_("Choose one of your expense approvers."))
    # HRMS enforces this setting only in its clients; enforce it here too.
    if not approver and approver_required():
        if not allowed:
            frappe.throw(_("No expense approver is set for you. Ask the office to set one on your Employee record."))
        frappe.throw(_("Select an expense approver."))
    doc.update({
        "employee": employee,
        "posting_date": values.get("posting_date") or nowdate(),
        "expense_approver": approver,
        "project": values.get("project") or None,
        "remark": plain_text(values.get("remark")),
    })
    rows = []
    for item in values.get("expenses") or []:
        amount = flt(item.get("amount"))
        rows.append({
            "expense_date": item.get("expense_date") or doc.posting_date,
            "expense_type": item.get("expense_type"),
            "description": escape_html(str(item.get("description") or "").strip()),
            "amount": amount,
            # Employees claim the full amount; the approver may sanction less.
            "sanctioned_amount": amount,
            "project": item.get("project") or doc.project,
        })
    if not rows:
        frappe.throw(_("Add at least one expense."))
    # Rows are rebuilt on every save; HRMS recalculates accounts and totals.
    doc.set("expenses", [])
    for row in rows:
        doc.append("expenses", row)


@frappe.whitelist(methods=["POST"])
def save_claim(values, client_token=None):
    """Create or update the employee's draft. Submission stays with the approver/workflow."""
    employee = require_expenses_enabled()
    values = parse(values)
    if values.get("name"):
        doc = own_claim(values["name"], employee)
        if doc.docstatus != 0:
            frappe.throw(_("Only draft claims can be edited."))
        ensure_not_stale(doc, values.get("modified"))
        apply_values(doc, values, employee)
        doc.save()
    else:
        def build():
            doc = frappe.new_doc(DOCTYPE)
            apply_values(doc, values, employee)
            return doc

        doc = idempotent_insert(client_token, build)
    return claim_payload(doc)


@frappe.whitelist(methods=["POST"])
def apply_action(name, action, modified=None):
    """Run a configured workflow transition (or an allowed submit) on an own claim."""
    employee = require_expenses_enabled()
    doc = own_claim(name, employee)
    ensure_not_stale(doc, modified)
    if get_workflow_name(DOCTYPE):
        from frappe.model.workflow import apply_workflow

        doc = apply_workflow(doc, action)
    elif action == "Submit":
        doc.submit()
    else:
        frappe.throw(_("This action is not available."))
    return claim_payload(frappe.get_doc(DOCTYPE, doc.name))


@frappe.whitelist(methods=["POST"])
def remove_receipt(name, file_name):
    doc = own_claim(name, require_expenses_enabled())
    if doc.docstatus != 0:
        frappe.throw(_("Receipts of a submitted claim cannot be removed."))
    remove_attachment(doc, file_name)
    return claim_payload(doc)


@frappe.whitelist(methods=["GET"])
def search_projects(txt=None, start=0, page_length=20):
    """Open Projects the user may select, for tagging expenses."""
    require_field_user()
    filters = {"status": ["not in", ["Completed", "Cancelled"]]}
    or_filters = None
    if txt:
        or_filters = {"name": ["like", f"%{txt}%"], "project_name": ["like", f"%{txt}%"]}
    return frappe.get_list(
        "Project", fields=["name", "project_name", "customer"], filters=filters, or_filters=or_filters,
        order_by="modified desc", limit_start=max(0, cint(start)),
        limit_page_length=min(50, max(1, cint(page_length) or 20)),
    )
