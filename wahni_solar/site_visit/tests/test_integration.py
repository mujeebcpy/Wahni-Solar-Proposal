"""Run on an explicitly selected, migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.site_visit.tests.test_integration.run
"""

import unittest
from io import BytesIO

import frappe
from frappe.utils import nowdate
from frappe.utils.file_manager import save_file
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from wahni_solar.site_visit import api
from wahni_solar.site_visit.doctype.pms_visit.pms_visit import COMPLETION_FIELDS
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
        self.assigned_employee = self.supervisor()[1]

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

    def assigned_site_visit(self):
        visit = api.make_site_visit(self.proposal.name)
        visit.site_visit_by = self.assigned_employee.name
        return visit

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
        visit = self.assigned_site_visit()
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
        visit = self.assigned_site_visit().insert()
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
        visit = self.assigned_site_visit().insert()
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
        visit = self.assigned_site_visit().insert()
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
        visit = self.assigned_site_visit().insert()
        self.assertEqual(visit.status, "Assigned")
        visit.customer_name = "Sales preparation"
        visit.roof_type = "Unauthorized technical edit"
        visit.save()
        self.assertEqual(visit.reload().customer_name, "Sales preparation")
        self.assertFalse(visit.roof_type)
        visit.status = "Completed"
        with self.assertRaises(frappe.PermissionError):
            visit.validate()

    def test_site_visit_assignment_can_be_saved_before_actual_visit(self):
        visit = self.assigned_site_visit().insert()
        self.assertEqual(visit.status, "Assigned")
        self.assertFalse(visit.visit_date)
        self.assertEqual(visit.owner, "Administrator")
        assigned_user = frappe.db.get_value("Employee", self.assigned_employee.name, "user_id")
        frappe.set_user(assigned_user)
        self.assertIn(visit.name, frappe.get_list(
            "Site Visit", filters={"site_visit_by": self.assigned_employee.name}, pluck="name"
        ))
        visit.reload()
        visit.status = "In Progress"
        visit.roof_type = "Sheet"
        visit.save()
        visit.status = "Completed"
        with self.assertRaises(frappe.ValidationError):
            visit.save()
        visit.reload()
        visit.status = "Completed"
        visit.visit_date = nowdate()
        visit.save()
        self.assertEqual(visit.reload().status, "Completed")

    def test_new_site_visit_requires_an_assignee(self):
        visit = api.make_site_visit(self.proposal.name)
        with self.assertRaises(frappe.ValidationError):
            visit.insert()

    def pms_photo(self):
        content = BytesIO()
        metadata = PngInfo()
        metadata.add_text("pms_test_token", self.token)
        Image.new("RGB", (1, 1), "white").save(content, format="PNG", pnginfo=metadata)
        return save_file(f"pms-test-{self.token}.png", content.getvalue(), None, None, is_private=1)

    def pms_document(self, **values):
        photo = self.pms_photo()
        if "service_person" not in values:
            values["service_person"] = self.supervisor()[1].name
        return frappe.get_doc({
            "doctype": "PMS Visit", "status": "Completed", "pms_date": nowdate(),
            "client_name": "", "place": "Test Place", "plant_capacity_kw": 8.5,
            "site_location_link": "https://maps.example.com/site", "inspection_remarks": "Test inspection",
            "ac_db_string_inverter": photo.file_url, "panel_image": photo.file_url, "house_image": photo.file_url,
            **values,
        })

    def test_pms_assignment_can_be_saved_and_completed_by_supervisor(self):
        user, employee = self.supervisor()
        project = self.fixture("Project", project_name="Assigned PMS Project", customer=self.customer.name,
                               company=self.company, status="Completed")
        visit = frappe.get_doc({
            "doctype": "PMS Visit", "project": project.name, "service_person": employee.name,
        }).insert()
        self.assertEqual(visit.status, "Assigned")
        self.assertEqual(visit.customer, self.customer.name)
        self.assertEqual(visit.owner, "Administrator")
        self.assertFalse(visit.pms_date)
        self.assertFalse(visit.panel_image)
        complete = self.pms_document(project=project.name, service_person=employee.name)
        frappe.set_user(user.name)
        self.assertIn(visit.name, frappe.get_list(
            "PMS Visit", filters={"service_person": employee.name}, pluck="name"
        ))
        visit.reload()
        visit.status = "In Progress"
        visit.place = "Site location"
        visit.save()
        visit.status = "Completed"
        with self.assertRaises(frappe.ValidationError):
            visit.save()
        visit.reload()
        visit.status = "Completed"
        visit.update({field: complete.get(field) for field in COMPLETION_FIELDS})
        visit.save()
        self.assertEqual(visit.reload().status, "Completed")

    def test_sales_can_assign_pms_but_cannot_complete_it(self):
        project = self.fixture("Project", project_name="Sales PMS Project", customer=self.customer.name,
                               company=self.company, status="Completed")
        sales = self.user("Sales User")
        complete = self.pms_document(project=project.name, service_person=self.assigned_employee.name)
        frappe.set_user(sales.name)
        visit = frappe.get_doc({
            "doctype": "PMS Visit", "project": project.name, "service_person": self.assigned_employee.name,
        }).insert()
        self.assertEqual(visit.status, "Assigned")
        visit.update({field: complete.get(field) for field in COMPLETION_FIELDS})
        visit.status = "Completed"
        with self.assertRaises(frappe.PermissionError):
            visit.save()

    def test_pms_project_requirement_status_and_client_autofill(self):
        project = self.fixture("Project", project_name="PMS Project", customer=self.customer.name,
                               company=self.company, status="Open")
        with self.assertRaises(frappe.ValidationError):
            self.pms_document().insert()
        with self.assertRaises(frappe.ValidationError):
            self.pms_document(project=project.name).insert()
        frappe.db.set_value("Project", project.name, "status", "Completed")
        visit = self.pms_document(project=project.name).insert()
        self.assertEqual(visit.client_name, self.customer.customer_name)
        self.assertEqual(visit.customer, self.customer.name)
        self.assertEqual(visit.plant_capacity_kw, 8.5)
        # A Project can have multiple maintenance visits.
        self.pms_document(project=project.name).insert()
        supervisor = self.user("Project Supervisor")
        frappe.set_user(supervisor.name)
        visit = frappe.get_doc("PMS Visit", visit.name)
        visit.inspection_remarks = "Supervisor update"
        visit.save()
        self.assertEqual(visit.reload().inspection_remarks, "Supervisor update")

    def test_pms_customer_or_client_and_employee_validation(self):
        project = self.fixture("Project", project_name="Customerless PMS Project", company=self.company, status="Completed")
        customer_visit = self.pms_document(project=project.name, customer=self.customer.name).insert()
        self.assertFalse(customer_visit.client_name)
        visit = self.pms_document(project=project.name, client_name="Manual client").insert()
        self.assertFalse(visit.customer)
        self.assertEqual(visit.client_name, "Manual client")
        self.assertEqual(visit.service_person_name, "Site Visit Test")
        with self.assertRaises(frappe.ValidationError):
            self.pms_document(project=project.name).insert()
        with self.assertRaises(frappe.ValidationError):
            self.pms_document(project=project.name, client_name="Manual client",
                              service_person=None, service_person_name="Free text").insert()
        user, employee = self.supervisor()
        for employee_status, enabled in (("Inactive", 1), ("Active", 0)):
            frappe.db.set_value("Employee", employee.name, "status", employee_status)
            frappe.db.set_value("User", user.name, "enabled", enabled)
            with self.subTest(status=employee_status, enabled=enabled), self.assertRaises(frappe.ValidationError):
                self.pms_document(project=project.name, client_name="Manual client", service_person=employee.name).insert()
        no_role = self.user("Sales User")
        frappe.db.set_value("Employee", employee.name, {"status": "Active", "user_id": no_role.name})
        with self.assertRaises(frappe.ValidationError):
            self.pms_document(project=project.name, client_name="Manual client", service_person=employee.name).insert()
        assigned_user = frappe.db.get_value("Employee", visit.service_person, "user_id")
        frappe.db.set_value("User", assigned_user, "enabled", 0)
        visit.inspection_remarks = "Historical assignment kept"
        visit.save()
        visit.service_person = None
        with self.assertRaises(frappe.ValidationError):
            visit.save()

    def test_existing_uat_pms_remains_editable_without_project_or_employee(self):
        # Represent an already copied UAT report, without running import code.
        visit = self.pms_document(client_name="Original Client", service_person=None,
                                  service_person_name="Old technician", legacy_site_data_collection=f"UAT-{self.token}")
        visit.name = f"_TEST-SV-{self.token}-pms"
        visit.db_insert()
        visit = frappe.get_doc("PMS Visit", visit.name)
        self.assertFalse(visit.project)
        self.assertFalse(visit.service_person)
        photo_url = visit.panel_image
        frappe.db.set_value("File", {"file_url": photo_url}, {
            "attached_to_doctype": "PMS Visit", "attached_to_name": visit.name, "attached_to_field": "panel_image",
        })
        supervisor = self.user("Project Supervisor")
        frappe.set_user(supervisor.name)
        visit.inspection_remarks = "Historical report updated"
        visit.save()
        self.assertEqual(visit.reload().service_person_name, "Old technician")
        self.assertEqual(visit.client_name, "Original Client")
        self.assertEqual(visit.panel_image, photo_url)
        self.assertTrue(frappe.db.exists("File", {"attached_to_doctype": "PMS Visit", "attached_to_name": visit.name,
                                                  "file_url": photo_url, "is_private": 1}))
        # A copied report cannot be used to create more project-less new reports.
        duplicate = frappe.copy_doc(visit)
        with self.assertRaises(frappe.ValidationError):
            duplicate.insert()
        from frappe.core.doctype.file.utils import find_file_by_url
        self.assertIsNotNone(find_file_by_url(photo_url))


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteVisitIntegration))
    if not result.wasSuccessful():
        raise AssertionError("Site Visit integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
