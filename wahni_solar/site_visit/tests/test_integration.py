"""Run on an explicitly selected, migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.site_visit.tests.test_integration.run
"""

import unittest

import frappe
from frappe.utils import nowdate

from wahni_solar.site_visit import api
from wahni_solar.wahni_solar_proposal.doctype.solar_proposal.solar_proposal import make_project


class TestSiteVisitIntegration(unittest.TestCase):
    def setUp(self):
        if not getattr(frappe.local, "site", None):
            self.skipTest("Requires an explicitly initialized, migrated Frappe site")
        self.original_user = frappe.session.user
        self.addCleanup(frappe.set_user, self.original_user)
        self.addCleanup(frappe.db.rollback)
        frappe.set_user("Administrator")
        self.token = frappe.generate_hash(length=10)
        self.company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
        self.assertTrue(self.company, "Create a Company before running these integration checks")
        # Source fixtures represent a saved legacy proposal. Insert them directly
        # so tests do not depend on live valuation, pricing, CRM or HR automation.
        self.lead = self.fixture("Lead", first_name="Site Visit Test", lead_name="Site Visit Test",
                                 mobile_no="9000000000", custom_kseb_consumer_no="001234", status="Lead")
        self.customer = self.fixture("Customer", customer_name="Site Visit Test", customer_type="Individual", lead_name=self.lead.name)
        self.proposal = self.new_proposal()

    def fixture(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, "name": f"_TEST-SV-{self.token}-{frappe.generate_hash(length=6)}", **values})
        doc.db_insert()
        return doc

    def new_proposal(self):
        return self.fixture(
            "Solar Proposal", proposal_to="Customer", party=self.customer.name, customer_name=self.customer.customer_name,
            company=self.company, currency=frappe.db.get_value("Company", self.company, "default_currency"),
            capacity_kw=5, calculation_version="Legacy", proposal_date=nowdate(),
            package_name=frappe.db.get_value("Solar Package", {}, "name"),
        )

    def user(self, *roles):
        email = f"site-visit-{self.token}-{frappe.generate_hash(length=5)}@example.com"
        user = self.fixture("User", name=email, email=email, first_name="Site Visit Test",
                            enabled=1, user_type="System User", send_welcome_email=0)
        for role in roles:
            self.fixture("Has Role", parent=user.name, parenttype="User", parentfield="roles", role=role)
        return user

    def supervisor(self):
        user = self.user("Project Supervisor")
        employee = self.fixture("Employee", first_name="Site Visit Test", employee_name="Site Visit Test",
                                company=self.company, status="Active", user_id=user.name)
        return user, employee

    def test_schema_role_and_navigation(self):
        self.assertEqual(frappe.get_meta("Site Visit").module, "Site Visit")
        self.assertTrue(frappe.db.exists("Module Def", "Site Visit"))
        self.assertTrue(frappe.db.exists("Role", "Project Supervisor"))
        self.assertTrue(frappe.db.exists("Workspace", "Site Visits"))
        self.assertFalse(frappe.db.exists("Workspace", "Site Visit"))
        self.assertEqual(frappe.db.get_value("Workspace", "Site Visits", "title"), "Site Visits")
        self.assertEqual(frappe.db.get_value("Sidebar", "Site Visits", "module"), "Site Visit")
        dock = frappe.get_doc("Dock", "wahni_solar")
        self.assertTrue(any(row.link_type == "Sidebar" and row.link_to == "Site Visits" for row in dock.items))
        field = frappe.get_meta("Project").get_field("custom_site_visit")
        self.assertEqual(field.options, "Site Visit")
        self.assertFalse(field.reqd)
        self.assertIn("custom_site_visit", [d.fieldname for d in frappe.get_meta("Project").fields])

    def test_autofill_unique_report_and_snapshot_preservation(self):
        visit = api.make_site_visit(self.proposal.name)
        self.assertTrue(visit.is_new())
        self.assertEqual((visit.lead, visit.customer), (self.lead.name, self.customer.name))
        self.assertEqual(visit.consumer_number, "001234")
        self.assertEqual(visit.requested_capacity_kw, 5)
        visit.insert()
        self.assertEqual(api.make_site_visit(self.proposal.name).name, visit.name)
        duplicate = frappe.copy_doc(visit)
        duplicate.solar_proposal = self.proposal.name
        with self.assertRaises(frappe.UniqueValidationError):
            duplicate.insert()
        visit.customer_name = "Corrected at site"
        visit.contact_number = "9111111111"
        visit.save()
        self.assertEqual(visit.reload().customer_name, "Corrected at site")
        self.assertEqual(visit.contact_number, "9111111111")

    def test_project_mapping_warning_optional_link_and_saved_relationship(self):
        frappe.clear_messages()
        missing = make_project(self.proposal.name)
        self.assertFalse(missing.custom_site_visit)
        self.assertTrue(frappe.message_log)
        missing.insert()
        visit = api.make_site_visit(self.proposal.name).insert()
        frappe.clear_messages()
        project = make_project(self.proposal.name)
        self.assertEqual(project.custom_site_visit, visit.name)
        self.assertTrue(frappe.message_log)
        self.assertFalse(frappe.db.exists("Project", {"custom_site_visit": visit.name}))
        project.project_name += f" {self.token}"
        project.insert()
        self.assertEqual(project.reload().custom_site_visit, visit.name)
        missing.reload().save()
        self.assertEqual(missing.custom_site_visit, visit.name)

    def test_completed_visit_maps_without_warning(self):
        user, employee = self.supervisor()
        visit = api.make_site_visit(self.proposal.name).insert()
        frappe.set_user(user.name)
        visit = frappe.get_doc("Site Visit", visit.name)
        visit.update({"status": "Completed", "site_visit_by": employee.name, "visit_date": nowdate()})
        visit.save()
        frappe.set_user("Administrator")
        frappe.clear_messages()
        project = make_project(self.proposal.name)
        self.assertEqual(project.custom_site_visit, visit.name)
        self.assertFalse(frappe.message_log)

    def test_cross_proposal_link_is_rejected_on_project_insert(self):
        visit = api.make_site_visit(self.proposal.name).insert()
        other = self.new_proposal()
        project = make_project(other.name)
        project.custom_site_visit = visit.name
        with self.assertRaises(frappe.ValidationError):
            project.insert()

    def test_employee_search_and_validation_use_real_user_roles(self):
        user, employee = self.supervisor()
        self.assertTrue(api.is_eligible_supervisor(employee.name))
        rows = api.supervisor_query("Employee", employee.name, "name", 0, 20, {})
        self.assertEqual([row[0] for row in rows], [employee.name])
        frappe.db.set_value("User", user.name, "enabled", 0)
        self.assertFalse(api.is_eligible_supervisor(employee.name))
        self.assertFalse(api.supervisor_query("Employee", employee.name, "name", 0, 20, {}))
        visit = api.make_site_visit(self.proposal.name)
        visit.site_visit_by = employee.name
        with self.assertRaises(frappe.ValidationError):
            visit.insert()

    def test_sales_can_prepare_but_not_edit_technical_fields(self):
        sales = self.user("Sales User")
        frappe.set_user(sales.name)
        visit = api.make_site_visit(self.proposal.name).insert()
        self.assertEqual(visit.status, "Draft")
        visit.customer_name = "Sales preparation"
        visit.roof_type = "Unauthorized technical edit"
        visit.save()
        self.assertEqual(visit.reload().customer_name, "Sales preparation")
        self.assertFalse(visit.roof_type)
        visit.status = "Completed"
        with self.assertRaises(frappe.PermissionError):
            visit.validate()


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteVisitIntegration))
    if not result.wasSuccessful():
        raise AssertionError("Site Visit integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
