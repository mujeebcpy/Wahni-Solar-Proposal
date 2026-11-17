"""Temporary, committed users for browser checks of /field. Always run teardown.

bench --site <site> execute wahni_solar.field_portal.tests.e2e_fixtures.setup --kwargs "{'password': '...'}"
bench --site <site> execute wahni_solar.field_portal.tests.e2e_fixtures.teardown
"""

import frappe
from frappe.utils.password import update_password

PREFIX = "field-e2e-"
DOMAIN = "@example.com"
USERS = {
    "supervisor": ("Project Supervisor", "Employee"),
    "noemployee": ("Employee",),
    "approver": ("Expense Approver",),
}


def email(kind):
    return f"{PREFIX}{kind}{DOMAIN}"


def setup(password):
    teardown()
    company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
    employees = {}
    # The approver must exist before the supervisor's Employee references it.
    for kind, roles in sorted(USERS.items(), key=lambda item: item[0] != "approver"):
        user = frappe.get_doc({
            "doctype": "User", "email": email(kind), "first_name": f"Field E2E {kind}",
            "send_welcome_email": 0, "user_type": "System User",
            "roles": [{"role": role} for role in roles],
        }).insert(ignore_permissions=True)
        update_password(user.name, password)
        if kind == "supervisor":
            employee = frappe.get_doc({
                "doctype": "Employee", "first_name": "Field E2E", "last_name": "Supervisor",
                "gender": frappe.db.get_value("Gender", {}, "name"), "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01", "company": company, "status": "Active", "user_id": user.name,
                "designation": frappe.db.get_value("Designation", {}, "name"),
                "expense_approver": email("approver"),
            })
            employee.flags.ignore_mandatory = True
            employee.insert(ignore_permissions=True)
            employees[kind] = employee.name
    frappe.db.commit()
    return {"users": {kind: email(kind) for kind in USERS}, "employees": employees}


FIXTURE_PREFIX = "_E2E-FIELD-"


def visit_fixtures():
    """Office-prepared visits and free proposals for the browser checks."""
    from frappe.utils import nowdate

    company = frappe.db.get_value("Employee", {"user_id": email("supervisor")}, "company")
    supervisor = frappe.db.get_value("Employee", {"user_id": email("supervisor")}, "name")
    other = frappe.db.get_value("Employee", {"user_id": ["!=", email("supervisor")], "status": "Active"}, "name")

    def insert(doctype, name, **values):
        doc = frappe.get_doc({"doctype": doctype, "name": f"{FIXTURE_PREFIX}{name}", **values})
        doc.db_insert()
        return doc

    customer = insert("Customer", "CUST", customer_name="E2E Field Customer", customer_type="Individual",
                      mobile_no="9000011111")
    proposals = []
    for index in range(3):
        proposals.append(insert(
            "Solar Proposal", f"SP-{index}", proposal_to="Customer", party=customer.name,
            customer_name=f"E2E Field Customer {index}", company=company, capacity_kw=5,
            currency=frappe.db.get_value("Company", company, "default_currency"), calculation_version="Legacy",
            proposal_date=nowdate(), package_name=frappe.db.get_value("Solar Package", {}, "name"),
        ).name)
    from wahni_solar.site_visit.api import make_site_visit

    visits = {}
    for key, proposal, employee in (("mine", proposals[0], supervisor), ("other", proposals[1], other)):
        visit = make_site_visit(proposal)
        visit.site_visit_by = employee
        visit.contact_number = "9000011111"
        visit.address = "Near Town Hall\nThrissur"
        visit.flags.ignore_permissions = True
        visit.insert()
        visits[key] = visit.name
    project = insert("Project", "PRJ", project_name="E2E Field Project", customer=customer.name,
                     company=company, status="Completed")
    pms = frappe.get_doc({"doctype": "PMS Visit", "project": project.name, "service_person": supervisor,
                          "place": "Thrissur"})
    pms.flags.ignore_permissions = True
    pms.insert()
    visits["pms"] = pms.name
    frappe.db.commit()
    return {"proposals": proposals, "free_proposal": proposals[2], "visits": visits, "project": project.name}


def teardown():
    for doctype in ("Site Visit", "PMS Visit"):
        field = "solar_proposal" if doctype == "Site Visit" else "project"
        for name in frappe.get_all(doctype, filters={field: ["like", f"{FIXTURE_PREFIX}%"]}, pluck="name"):
            for file in frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name}, pluck="name"):
                frappe.delete_doc("File", file, force=True, ignore_permissions=True)
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
    for doctype in ("Solar Proposal", "Project", "Customer"):
        for name in frappe.get_all(doctype, filters={"name": ["like", f"{FIXTURE_PREFIX}%"]}, pluck="name"):
            frappe.db.delete(doctype, {"name": name})
    for kind in USERS:
        user = email(kind)
        for name in frappe.get_all("Employee", filters={"user_id": user}, pluck="name"):
            for doctype in ("Site Visit", "PMS Visit", "Expense Claim"):
                field = {"Site Visit": "site_visit_by", "PMS Visit": "service_person", "Expense Claim": "employee"}[doctype]
                for record in frappe.get_all(doctype, filters={field: name}, fields=["name", "docstatus"]):
                    if record.docstatus == 1:
                        frappe.get_doc(doctype, record.name).cancel()
                    frappe.delete_doc(doctype, record.name, force=True, ignore_permissions=True)
            frappe.delete_doc("Employee", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("File", filters={"owner": user}, pluck="name"):
            frappe.delete_doc("File", name, force=True, ignore_permissions=True)
        if frappe.db.exists("User", user):
            frappe.delete_doc("User", user, force=True, ignore_permissions=True)
    frappe.db.commit()
    return "removed"
