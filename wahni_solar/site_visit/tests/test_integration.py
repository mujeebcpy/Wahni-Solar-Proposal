"""Run on an explicitly selected, migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.site_visit.tests.test_integration.run
"""

import unittest
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.utils import nowdate
from frappe.utils.file_manager import save_file
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from wahni_solar.site_visit import api
from wahni_solar.site_visit import migrate_pms
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
            "doctype": "PMS Visit", "pms_date": nowdate(),
            "client_name": "", "place": "Test Place", "plant_capacity_kw": 8.5,
            "site_location_link": "https://maps.example.com/site", "inspection_remarks": "Test inspection",
            "ac_db_string_inverter": photo.file_url, "panel_image": photo.file_url, "house_image": photo.file_url,
            **values,
        })

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
        # Repeated service visits must not collide on a blank migration reference.
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

    def test_legacy_pms_copy_preserves_photos_history_and_project_exception(self):
        source_file = self.pms_photo()
        source = frappe._dict({
            "name": f"_TEST-SV-{self.token}-10/26-01", "pms_date": nowdate(), "service_person_name": "Old technician",
            "client_name": "Original Client", "place": "Old Place", "plant_capacity_kw": 7.25,
            "site_location_link": "https://maps.example.com/old", "inspection_remarks": "Historical report",
            "ac_db_string_inverter": source_file.file_url, "panel_image": source_file.file_url,
            "house_image": source_file.file_url, "owner": "Administrator", "creation": "2026-10-14 12:54:47",
            "modified": "2026-10-20 09:18:18", "modified_by": "Administrator",
        })
        # The development site intentionally has no legacy DocType. Simulate only
        # its read side; PMS insertion, File copies and permissions use the real DB.
        get_all, get_meta, exists = frappe.get_all, frappe.get_meta, frappe.db.exists
        def legacy_rows(doctype, *args, **kwargs):
            return [source] if doctype == migrate_pms.SOURCE else get_all(doctype, *args, **kwargs)
        def legacy_meta(doctype, *args, **kwargs):
            return get_meta("PMS Visit" if doctype == migrate_pms.SOURCE else doctype, *args, **kwargs)
        def legacy_exists(doctype, name=None, *args, **kwargs):
            if doctype == "DocType" and name == migrate_pms.SOURCE:
                return True
            return exists(doctype, name, *args, **kwargs)
        with patch.object(frappe, "get_all", side_effect=legacy_rows), \
                patch.object(frappe, "get_meta", side_effect=legacy_meta), \
                patch.object(frappe.db, "exists", side_effect=legacy_exists):
            self.assertEqual(migrate_pms.migrate()["ready"], 1)
            self.assertEqual(migrate_pms.migrate(dry_run=False)["copied"], 1)
            self.assertEqual(migrate_pms.migrate(dry_run=False)["already_copied"], 1)
        visit = frappe.get_doc("PMS Visit", source.name)
        self.assertFalse(visit.project)
        self.assertEqual(visit.client_name, "Original Client")
        self.assertEqual(visit.service_person_name, "Old technician")
        self.assertFalse(visit.service_person)
        self.assertEqual(visit.plant_capacity_kw, 7.25)
        self.assertEqual(str(visit.creation), source.creation)
        self.assertEqual(visit.panel_image, source_file.file_url)
        self.assertFalse(source_file.reload().attached_to_doctype)
        self.assertTrue(frappe.db.exists("File", {"attached_to_doctype": "PMS Visit", "attached_to_name": visit.name,
                                                  "file_url": source_file.file_url, "is_private": 1}))
        visit.inspection_remarks = "Historical report updated"
        visit.save()
        # A copied report cannot be used to create more project-less new reports.
        duplicate = frappe.copy_doc(visit)
        with self.assertRaises(frappe.ValidationError):
            duplicate.insert()
        supervisor = self.user("Project Supervisor")
        frappe.set_user(supervisor.name)
        from frappe.core.doctype.file.utils import find_file_by_url
        self.assertIsNotNone(find_file_by_url(source_file.file_url))


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteVisitIntegration))
    if not result.wasSuccessful():
        raise AssertionError("Site Visit integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
