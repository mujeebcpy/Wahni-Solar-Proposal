"""Wahni Field visit APIs on a migrated site; all test records are rolled back.

bench --site <site> execute wahni_solar.field_portal.tests.test_visits_integration.run
"""

import unittest

import frappe
from frappe.utils import add_days, nowdate
from frappe.utils.file_manager import save_file

from wahni_solar.field_portal import visits
from wahni_solar.field_portal.tests.test_access_integration import TestFieldAccess


class TestFieldVisits(TestFieldAccess):
    def field_names(self, payload):
        return {field["fieldname"]: field for field in payload["fields"]}

    # ---- Site Visits ----
    def test_admin_created_visit_is_listed_for_assignee(self):
        user, employee = self.field_user()
        _other_user, other = self.field_user()
        mine, theirs = self.site_visit_for(employee), self.site_visit_for(other)
        self.assertEqual(mine.owner, "Administrator")
        frappe.set_user(user)
        names = [row.name for row in visits.list_visits("Site Visit")]
        self.assertIn(mine.name, names)
        self.assertNotIn(theirs.name, names)
        self.assertIn(mine.name, [row.name for row in visits.list_visits("Site Visit", status="Assigned")])
        self.assertNotIn(mine.name, [row.name for row in visits.list_visits("Site Visit", status="Completed")])
        self.assertIn(mine.name, [row.name for row in visits.list_visits("Site Visit", txt=self.customer.customer_name)])
        with self.assertRaises(frappe.PermissionError):
            visits.get_visit("Site Visit", theirs.name)
        with self.assertRaises(frappe.PermissionError):
            visits.save_visit("Site Visit", theirs.name, {"roof_type": "x"})
        with self.assertRaises(frappe.ValidationError):
            visits.list_visits("Employee")

    def test_office_supervisor_portal_list_is_still_own_work(self):
        user, employee = self.field_user("Projects Manager")
        other = self.site_visit_for(self.field_user()[1])
        mine = self.site_visit_for(employee)
        frappe.set_user(user)
        names = [row.name for row in visits.list_visits("Site Visit")]
        self.assertEqual(names.count(mine.name), 1)
        self.assertNotIn(other.name, names)

    def test_payload_is_metadata_driven_and_protects_source_fields(self):
        user, employee = self.field_user()
        visit = self.site_visit_for(employee)
        frappe.set_user(user)
        payload = visits.get_visit("Site Visit", visit.name)
        fields = self.field_names(payload)
        self.assertEqual([s["key"] for s in payload["steps"]], ["customer", "location", "site", "measurements", "drawings"])
        for protected in ("solar_proposal", "site_visit_by", "status", "customer", "lead"):
            self.assertTrue(fields[protected]["read_only"], protected)
        self.assertFalse(fields["roof_type"]["read_only"])  # permlevel 1, supervisors may write
        self.assertEqual(fields["roof_type"]["step"], "site")
        self.assertEqual(fields["building_outline"]["step"], "drawings")
        self.assertEqual(fields["visit_date"]["mandatory_depends_on"], "eval:doc.status == 'Completed'")
        self.assertEqual(payload["values"]["customer_name"], self.customer.customer_name)
        self.assertEqual(payload["assignee"], employee)
        self.assertTrue(payload["editable"])

    def test_metadata_changes_are_reflected_without_frontend_changes(self):
        user, employee = self.field_user()
        visit = self.site_visit_for(employee)
        for prop, value, fieldname in (("label", "Roof Material", "roof_type"), ("hidden", "1", "soil_type")):
            frappe.get_doc({"doctype": "Property Setter", "doc_type": "Site Visit", "doctype_or_field": "DocField",
                            "field_name": fieldname, "property": prop, "value": value,
                            "property_type": "Data" if prop == "label" else "Check"}).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Site Visit")
        self.addCleanup(frappe.clear_cache, doctype="Site Visit")
        frappe.set_user(user)
        fields = self.field_names(visits.get_visit("Site Visit", visit.name))
        self.assertEqual(fields["roof_type"]["label"], "Roof Material")
        self.assertNotIn("soil_type", fields)  # hidden fields are never exposed
        frappe.db.rollback()
        frappe.clear_cache(doctype="Site Visit")

    def test_save_progress_ignores_protected_fields(self):
        user, employee = self.field_user()
        _other_user, other = self.field_user()
        visit = self.site_visit_for(employee)
        frappe.set_user(user)
        payload = visits.get_visit("Site Visit", visit.name)
        result = visits.save_visit("Site Visit", visit.name, {
            "roof_type": "Sheet", "number_of_pits": "3", "site_visit_by": other, "status": "Completed",
            "solar_proposal": self.new_proposal().name, "building_outline": "/files/forged.png",
        }, modified=payload["modified"])
        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(result["values"]["roof_type"], "Sheet")
        self.assertEqual(result["values"]["number_of_pits"], 3)
        self.assertEqual(sorted(result["ignored_fields"]), ["building_outline", "site_visit_by", "solar_proposal", "status"])
        stored = frappe.db.get_value("Site Visit", visit.name, ["site_visit_by", "status", "building_outline"], as_dict=True)
        self.assertEqual((stored.site_visit_by, stored.status, stored.building_outline), (employee, "In Progress", None))
        with self.assertRaises(frappe.TimestampMismatchError):
            visits.save_visit("Site Visit", visit.name, {"roof_type": "Tile"}, modified=payload["modified"])

    def test_completion_uses_server_rules_then_locks(self):
        user, employee = self.field_user()
        visit = self.site_visit_for(employee)
        frappe.set_user(user)
        modified = visits.get_visit("Site Visit", visit.name)["modified"]
        with self.assertRaises(frappe.ValidationError):
            visits.save_visit("Site Visit", visit.name, {"roof_type": "Sheet"}, modified=modified, action="complete")
        self.assertEqual(frappe.db.get_value("Site Visit", visit.name, "status"), "Assigned")
        done = visits.save_visit("Site Visit", visit.name, {"visit_date": nowdate()}, modified=modified, action="complete")
        self.assertEqual(done["status"], "Completed")
        self.assertFalse(done["editable"])
        self.assertTrue(all(field["read_only"] for field in done["fields"]))
        with self.assertRaises(frappe.PermissionError):
            visits.save_visit("Site Visit", visit.name, {"roof_type": "Tile"}, modified=done["modified"])

    def test_create_from_proposal_is_self_assigned_and_unique(self):
        user, employee = self.field_user()
        other_user, _other = self.field_user()
        proposal = self.new_proposal()
        frappe.set_user(user)
        self.assertIn(proposal.name, [r["name"] for r in visits.search_proposals(proposal.name)])
        created = visits.create_site_visit(proposal.name, client_token=f"sv-{self.token}")
        self.assertFalse(created["existing"])
        self.assertEqual(frappe.db.get_value("Site Visit", created["name"], "site_visit_by"), employee)
        self.assertEqual(visits.create_site_visit(proposal.name, client_token=f"sv-{self.token}")["name"], created["name"])
        self.assertTrue(visits.create_site_visit(proposal.name)["existing"])
        self.assertNotIn(proposal.name, [r["name"] for r in visits.search_proposals(proposal.name)])
        frappe.set_user(other_user)
        with self.assertRaises(frappe.DuplicateEntryError) as error:
            visits.create_site_visit(proposal.name)
        self.assertNotIn(created["name"], str(error.exception))

    def test_office_supervisor_creating_in_portal_is_assigned_to_self(self):
        user, employee = self.field_user("Projects Manager")
        frappe.set_user(user)
        created = visits.create_site_visit(self.new_proposal().name)
        self.assertEqual(frappe.db.get_value("Site Visit", created["name"], "site_visit_by"), employee)

    def test_drawing_attachment_binding(self):
        user, employee = self.field_user()
        other_user, other = self.field_user()
        visit = self.site_visit_for(employee)
        frappe.set_user(user)
        modified = visits.get_visit("Site Visit", visit.name)["modified"]
        drawing = save_file(f"outline-{self.token}.png", b"png", "Site Visit", visit.name, is_private=1)
        public = save_file(f"public-{self.token}.png", b"png", "Site Visit", visit.name, is_private=0)
        with self.assertRaises(frappe.ValidationError):
            visits.set_attachment("Site Visit", visit.name, "building_outline", public.file_url, modified=modified)
        with self.assertRaises(frappe.PermissionError):
            visits.set_attachment("Site Visit", visit.name, "status", drawing.file_url, modified=modified)
        bound = visits.set_attachment("Site Visit", visit.name, "building_outline", drawing.file_url, modified=modified)
        self.assertEqual(bound["values"]["building_outline"], drawing.file_url)
        self.assertEqual(bound["status"], "In Progress")
        self.assertIn(drawing.name, [f.name for f in bound["attachments"]])
        frappe.set_user(other_user)
        self.assertFalse(frappe.get_doc("File", drawing.name).has_permission("read"))
        frappe.set_user(user)
        replacement = save_file(f"outline2-{self.token}.png", b"png2", "Site Visit", visit.name, is_private=1)
        replaced = visits.set_attachment("Site Visit", visit.name, "building_outline", replacement.file_url, modified=bound["modified"])
        self.assertFalse(frappe.db.exists("File", drawing.name))  # replaced, unreferenced file removed
        cleared = visits.clear_attachment("Site Visit", visit.name, "building_outline", modified=replaced["modified"])
        self.assertIsNone(cleared["values"]["building_outline"])
        self.assertFalse(frappe.db.exists("File", replacement.name))
        stray = save_file(f"stray-{self.token}.png", b"png3", "Site Visit", visit.name, is_private=1)
        visits.discard_upload("Site Visit", visit.name, stray.name)
        self.assertFalse(frappe.db.exists("File", stray.name))

    # ---- PMS Visits ----
    def test_pms_create_list_and_multiple_visits_per_project(self):
        user, employee = self.field_user()
        _other_user, other = self.field_user()
        project = self.completed_project()
        open_project = self.fixture("Project", project_name=f"Field Open {self.token}", customer=self.customer.name,
                                    company=self.company, status="Open")
        office = self.pms_for(employee, project)
        theirs = self.pms_for(other, project)
        frappe.set_user(user)
        found = [p.name for p in visits.search_completed_projects(self.token)]
        self.assertIn(project.name, found)
        self.assertNotIn(open_project.name, found)
        self.assertEqual(visits.search_completed_projects(project.name)[0].customer_name, self.customer.customer_name)
        first = visits.create_pms_visit(project.name, client_token=f"pms-{self.token}")
        self.assertEqual(visits.create_pms_visit(project.name, client_token=f"pms-{self.token}")["name"], first["name"])
        second = visits.create_pms_visit(project.name)
        self.assertNotEqual(first["name"], second["name"])
        for name in (first["name"], second["name"]):
            values = frappe.db.get_value("PMS Visit", name, ["service_person", "customer", "client_name", "status"], as_dict=True)
            self.assertEqual((values.service_person, values.customer, values.status), (employee, self.customer.name, "Assigned"))
            self.assertEqual(values.client_name, self.customer.customer_name)
        names = [row.name for row in visits.list_visits("PMS Visit")]
        self.assertTrue({office.name, first["name"], second["name"]} <= set(names))
        self.assertNotIn(theirs.name, names)
        with self.assertRaises(frappe.ValidationError):
            visits.create_pms_visit(open_project.name)

    def test_pms_photos_progress_and_completion(self):
        user, employee = self.field_user()
        visit = self.pms_for(employee)
        frappe.set_user(user)
        payload = visits.get_visit("PMS Visit", visit.name)
        fields = self.field_names(payload)
        self.assertEqual([s["key"] for s in payload["steps"]], ["details", "photos", "remarks"])
        for protected in ("project", "service_person", "customer", "status", "legacy_site_data_collection"):
            if protected in fields:
                self.assertTrue(fields[protected]["read_only"], protected)
        for photo in ("ac_db_string_inverter", "panel_image", "house_image", "additional_image"):
            self.assertEqual(fields[photo]["step"], "photos")
            self.assertEqual(fields[photo]["fieldtype"], "Attach Image")
        self.assertEqual(fields["panel_image"]["mandatory_depends_on"], "eval:doc.status == 'Completed'")
        self.assertFalse(fields["additional_image"]["mandatory_depends_on"])
        progress = visits.save_visit("PMS Visit", visit.name, {"place": "Thrissur", "plant_capacity_kw": 7.5},
                                     modified=payload["modified"])
        self.assertEqual(progress["status"], "In Progress")
        with self.assertRaises(frappe.ValidationError):
            visits.save_visit("PMS Visit", visit.name, {}, modified=progress["modified"], action="complete")
        modified = progress["modified"]
        for field in ("ac_db_string_inverter", "panel_image", "house_image"):
            photo = save_file(f"{field}-{self.token}.png", field.encode(), "PMS Visit", visit.name, is_private=1)
            modified = visits.set_attachment("PMS Visit", visit.name, field, photo.file_url, modified=modified)["modified"]
        done = visits.save_visit("PMS Visit", visit.name, {
            "pms_date": nowdate(), "site_location_link": "https://maps.example.com/x", "inspection_remarks": "All good",
        }, modified=modified, action="complete")
        self.assertEqual(done["status"], "Completed")
        self.assertEqual(done["values"]["plant_capacity_kw"], 7.5)
        self.assertFalse(done["editable"])


def run():
    names = sorted(name for name in vars(TestFieldVisits) if name.startswith("test_"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(TestFieldVisits(name) for name in names))
    if not result.wasSuccessful():
        raise AssertionError("Field visit integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
