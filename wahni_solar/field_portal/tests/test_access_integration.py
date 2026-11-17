"""Field-portal access policy on a migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.field_portal.tests.test_access_integration.run
"""

import unittest

import frappe
from frappe.utils import nowdate
from frappe.utils.file_manager import save_file

from wahni_solar.field_portal import access
from wahni_solar.site_visit import api
from wahni_solar.site_visit.tests.test_integration import TestSiteVisitIntegration


class TestFieldAccess(TestSiteVisitIntegration):
    """Reuses the Site Visit fixtures; run() loads only the tests declared here."""

    def field_user(self, *extra_roles):
        # Real supervisors also hold Employee, which grants Project/Customer select.
        user = self.user("Project Supervisor", "Employee", *extra_roles)
        employee = self.fixture("Employee", first_name="Field Test", employee_name="Field Test",
                                company=self.company, status="Active", user_id=user.name)
        return user.name, employee.name

    def completed_project(self):
        return self.fixture("Project", project_name=f"Field PMS {self.token} {frappe.generate_hash(length=6)}", customer=self.customer.name,
                            company=self.company, status="Completed")

    def site_visit_for(self, employee, proposal=None):
        visit = api.make_site_visit((proposal or self.new_proposal()).name)
        visit.site_visit_by = employee
        return visit.insert()

    def pms_for(self, employee, project=None):
        return frappe.get_doc({"doctype": "PMS Visit", "project": (project or self.completed_project()).name,
                               "service_person": employee}).insert()

    def test_restricted_supervisor_sees_only_assigned_visits_everywhere(self):
        user_a, emp_a = self.field_user()
        _user_b, emp_b = self.field_user()
        mine, theirs = self.site_visit_for(emp_a), self.site_visit_for(emp_b)
        pms_mine, pms_theirs = self.pms_for(emp_a), self.pms_for(emp_b)
        self.assertEqual(mine.owner, "Administrator")
        frappe.set_user(user_a)
        visible = frappe.get_list("Site Visit", pluck="name", limit_page_length=0)
        self.assertIn(mine.name, visible)
        self.assertNotIn(theirs.name, visible)
        visible = frappe.get_list("PMS Visit", pluck="name", limit_page_length=0)
        self.assertIn(pms_mine.name, visible)
        self.assertNotIn(pms_theirs.name, visible)
        # Forged filters cannot widen the list.
        self.assertFalse(frappe.get_list("Site Visit", filters={"site_visit_by": emp_b}, pluck="name"))
        for doc in (theirs, pms_theirs):
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc(doc.doctype, doc.name).check_permission("read")
            with self.assertRaises(frappe.PermissionError):
                frappe.client.get(doc.doctype, doc.name)
            self.assertFalse(frappe.has_permission(doc.doctype, "read", doc=doc.name))
        self.assertTrue(frappe.has_permission("Site Visit", "write", doc=mine.name))

    def test_private_files_follow_visit_assignment(self):
        user_a, emp_a = self.field_user()
        user_b, emp_b = self.field_user()
        theirs = self.site_visit_for(emp_b)
        attached = save_file(f"field-{self.token}.txt", b"drawing", "Site Visit", theirs.name, is_private=1)
        frappe.set_user(user_a)
        self.assertFalse(frappe.get_doc("File", attached.name).has_permission("read"))
        frappe.set_user(user_b)
        self.assertTrue(frappe.get_doc("File", attached.name).has_permission("read"))

    def test_self_assignment_and_forged_employee(self):
        user_a, emp_a = self.field_user()
        _user_b, emp_b = self.field_user()
        frappe.set_user(user_a)
        # A supervisor cannot read proposals, yet can create from one with a limited snapshot.
        proposal = self.new_proposal()
        self.assertFalse(frappe.has_permission("Solar Proposal", "read", doc=proposal.name))
        self.assertIn(proposal.name, [row[0] for row in api.proposal_query("Solar Proposal", proposal.name, "name", 0, 100, {})])
        visit = api.make_site_visit(proposal.name).insert()
        self.assertEqual(visit.site_visit_by, emp_a)
        self.assertEqual(visit.customer_name, self.customer.customer_name)
        self.assertNotIn(proposal.name, [row[0] for row in api.proposal_query("Solar Proposal", proposal.name, "name", 0, 100, {})])
        forged = api.make_site_visit(self.new_proposal().name)
        forged.site_visit_by = emp_b
        with self.assertRaises(frappe.PermissionError):
            forged.insert()
        pms = frappe.get_doc({"doctype": "PMS Visit", "project": self.completed_project().name}).insert()
        self.assertEqual(pms.service_person, emp_a)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "PMS Visit", "project": self.completed_project().name,
                            "service_person": emp_b}).insert()
        self.assertEqual([row[0] for row in api.supervisor_query("Employee", "", "name", 0, 100, {})], [emp_a])

    def test_existing_inaccessible_report_is_not_revealed(self):
        user_a, _emp_a = self.field_user()
        _user_b, emp_b = self.field_user()
        proposal = self.new_proposal()
        theirs = self.site_visit_for(emp_b, proposal)
        frappe.set_user(user_a)
        with self.assertRaises(frappe.DuplicateEntryError) as error:
            api.make_site_visit(proposal.name)
        self.assertNotIn(theirs.name, str(error.exception))
        self.assertNotIn(proposal.name, [row[0] for row in api.proposal_query("Solar Proposal", proposal.name, "name", 0, 100, {})])

    def test_restricted_supervisor_cannot_reassign_or_change_project(self):
        user_a, emp_a = self.field_user()
        _user_b, emp_b = self.field_user()
        visit, pms = self.site_visit_for(emp_a), self.pms_for(emp_a)
        frappe.set_user(user_a)
        visit.reload()
        visit.site_visit_by = emp_b
        with self.assertRaises(frappe.PermissionError):
            visit.save()
        pms.reload()
        pms.project = self.completed_project().name
        with self.assertRaises(frappe.PermissionError):
            pms.save()

    def test_completed_visit_is_locked_until_office_reopens(self):
        user_a, emp_a = self.field_user()
        _user_b, emp_b = self.field_user()
        visit = self.site_visit_for(emp_a)
        frappe.set_user(user_a)
        visit.reload()
        visit.update({"status": "Completed", "visit_date": nowdate()})
        visit.save()
        self.assertFalse(frappe.has_permission("Site Visit", "write", doc=visit.name))
        self.assertTrue(frappe.has_permission("Site Visit", "read", doc=visit.name))
        visit.reload()
        visit.roof_type = "Edited after completion"
        with self.assertRaises(frappe.PermissionError):
            visit.save()
        sales = self.user("Sales User")
        frappe.set_user(sales.name)
        self.assertFalse(frappe.has_permission("Site Visit", "write", doc=visit.name))
        manager = self.user("Projects Manager")
        frappe.set_user(manager.name)
        visit.reload()
        visit.status = "In Progress"
        visit.site_visit_by = emp_b
        visit.save()
        self.assertEqual(visit.reload().status, "In Progress")
        self.assertEqual(visit.site_visit_by, emp_b)

    def test_mixed_roles(self):
        sales_supervisor, emp = self.field_user("Sales User")
        self.assertTrue(access.is_restricted(sales_supervisor))
        office_supervisor, _office_emp = self.field_user("Projects Manager")
        self.assertFalse(access.is_restricted(office_supervisor))
        other = self.site_visit_for(self.field_user()[1])
        frappe.set_user(sales_supervisor)
        self.assertNotIn(other.name, frappe.get_list("Site Visit", pluck="name", limit_page_length=0))
        frappe.set_user(office_supervisor)
        self.assertIn(other.name, frappe.get_list("Site Visit", pluck="name", limit_page_length=0))
        # Sales users without the supervisor role keep their existing access.
        frappe.set_user(self.user("Sales User").name)
        self.assertIn(other.name, frappe.get_list("Site Visit", pluck="name", limit_page_length=0))

    def test_portal_gate(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            access.require_field_user()
        frappe.set_user(self.user("Project Supervisor").name)  # no Employee
        with self.assertRaises(frappe.PermissionError):
            access.require_field_user()
        frappe.set_user(self.user("Employee").name)
        with self.assertRaises(frappe.PermissionError):
            access.require_field_user()
        user, employee = self.field_user()
        frappe.set_user(user)
        self.assertEqual(access.require_field_user(), employee)


def run():
    names = sorted(name for name in vars(TestFieldAccess) if name.startswith("test_"))
    suite = unittest.TestSuite(TestFieldAccess(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Field access integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
