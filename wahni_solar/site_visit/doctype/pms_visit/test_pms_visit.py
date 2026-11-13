import json
import unittest
from inspect import unwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.site_visit.doctype.pms_visit import pms_visit
from wahni_solar.site_visit import migrate_pms


class Record(frappe._dict):
    def get_doc_before_save(self):
        return self.get("previous")


class TestPMSVisit(unittest.TestCase):
    def setUp(self):
        translation = patch.object(pms_visit, "_", side_effect=lambda text: text)
        translation.start()
        self.addCleanup(translation.stop)
        mock = patch.object(pms_visit, "frappe")
        self.frappe = mock.start()
        self.addCleanup(mock.stop)
        self.frappe.flags = frappe._dict()
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.get_doc.return_value = Record(status="Completed", customer="CUSTOMER", check_permission=lambda permission: None)
        eligible = patch.object(pms_visit, "is_eligible_supervisor", return_value=True)
        self.eligible = eligible.start()
        self.addCleanup(eligible.stop)

    def valid_record(self, **values):
        return Record(project="PROJECT", customer="CUSTOMER", service_person="EMPLOYEE", **values)

    def test_new_visit_requires_project(self):
        with self.assertRaisesRegex(ValueError, "Project is required"):
            pms_visit.PMSVisit.validate(Record())

    def test_document_flags_or_legacy_reference_cannot_bypass_requirement(self):
        doc = Record(legacy_site_data_collection="OLD", flags={"in_legacy_pms_import": True})
        with self.assertRaisesRegex(ValueError, "migration command"):
            pms_visit.PMSVisit.validate(doc)

    def test_trusted_migration_accepts_old_report_without_project(self):
        self.frappe.flags.in_legacy_pms_import = True
        pms_visit.PMSVisit.validate(Record(legacy_site_data_collection="OLD", client_name="Old client", service_person_name="Old technician"))

    def test_existing_historical_report_remains_editable_without_project(self):
        previous = Record(legacy_site_data_collection="OLD", service_person_name="Old technician")
        pms_visit.PMSVisit.validate(Record(previous=previous, legacy_site_data_collection="OLD", client_name="Old client", service_person_name="Old technician"))

    def test_project_cannot_be_removed_once_linked_even_on_a_legacy_report(self):
        for legacy in (None, "OLD"):
            previous = Record(project="PROJECT", legacy_site_data_collection=legacy)
            with self.subTest(legacy=legacy), self.assertRaisesRegex(ValueError, "Project is required"):
                pms_visit.PMSVisit.validate(Record(previous=previous, legacy_site_data_collection=legacy))

    def test_legacy_reference_is_immutable(self):
        with self.assertRaisesRegex(ValueError, "cannot be changed"):
            pms_visit.PMSVisit.validate(Record(previous=Record(name="EXISTING"), legacy_site_data_collection="FORGED"))

    def test_project_validation_checks_completed_status(self):
        for status in ("Open", "Cancelled"):
            self.frappe.get_doc.return_value = Record(status=status, check_permission=lambda permission: None)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "completed Projects"):
                pms_visit.project_values("PROJECT")

    def test_project_fills_customer_name_and_keeps_capacity(self):
        self.frappe.get_doc.return_value = Record(status="Completed", customer="CUSTOMER", check_permission=lambda permission: None)
        self.frappe.db.get_value.return_value = "Customer's name"
        doc = Record(project="PROJECT", service_person="EMPLOYEE", plant_capacity_kw=7.5)
        pms_visit.PMSVisit.validate(doc)
        self.assertEqual(doc.client_name, "Customer's name")
        self.assertEqual(doc.customer, "CUSTOMER")
        self.assertEqual(doc.plant_capacity_kw, 7.5)

    def test_history_does_not_break_when_project_is_reopened(self):
        pms_visit.PMSVisit.validate(self.valid_record(previous=Record(project="PROJECT", service_person="EMPLOYEE", service_person_name="Technician")))
        self.frappe.get_doc.assert_not_called()

    def test_customer_or_client_name_is_accepted_and_preserved(self):
        for values in ({"customer": "CUSTOMER"}, {"client_name": "Manual client"}):
            doc = Record(project="PROJECT", service_person="EMPLOYEE", **values)
            pms_visit.PMSVisit.validate(doc)
            for field, value in values.items():
                self.assertEqual(doc[field], value)

    def test_customerless_project_allows_manual_client_name(self):
        self.frappe.get_doc.return_value = Record(status="Completed", check_permission=lambda permission: None)
        self.assertEqual(pms_visit.project_values("PROJECT"), {"customer": None, "client_name": None})
        doc = Record(project="PROJECT", client_name="Manual client", service_person="EMPLOYEE")
        pms_visit.PMSVisit.validate(doc)
        self.assertEqual(doc.client_name, "Manual client")

    def test_neither_customer_nor_client_is_rejected(self):
        doc = Record(project="PROJECT", previous=Record(project="PROJECT"), client_name="  ", service_person="EMPLOYEE")
        with self.assertRaisesRegex(ValueError, "Customer or enter a Client Name"):
            pms_visit.PMSVisit.validate(doc)

    def test_new_reports_cannot_use_only_free_text_service_person(self):
        doc = Record(project="PROJECT", customer="CUSTOMER", service_person_name="Not an Employee")
        with self.assertRaisesRegex(ValueError, "Select an Employee"):
            pms_visit.PMSVisit.validate(doc)

    def test_ineligible_employee_is_rejected(self):
        self.eligible.return_value = False
        with self.assertRaisesRegex(ValueError, "Project Supervisor role"):
            pms_visit.PMSVisit.validate(self.valid_record())

    def test_employee_name_is_copied_and_assignment_checked(self):
        self.frappe.db.get_value.return_value = "Technician"
        doc = self.valid_record()
        pms_visit.PMSVisit.validate(doc)
        self.eligible.assert_called_once_with("EMPLOYEE")
        self.assertEqual(doc.service_person_name, "Technician")

    def test_unchanged_employee_is_preserved_when_no_longer_eligible(self):
        self.eligible.return_value = False
        doc = self.valid_record(previous=Record(project="PROJECT", service_person="EMPLOYEE", service_person_name="Original technician"))
        pms_visit.PMSVisit.validate(doc)
        self.eligible.assert_not_called()
        self.assertEqual(doc.service_person_name, "Original technician")

    def test_assigned_employee_cannot_be_cleared(self):
        doc = Record(project="PROJECT", customer="CUSTOMER", service_person_name="Technician",
                     previous=Record(project="PROJECT", service_person="EMPLOYEE", service_person_name="Technician"))
        with self.assertRaisesRegex(ValueError, "Select an Employee"):
            pms_visit.PMSVisit.validate(doc)

    def test_preexisting_free_text_service_person_remains_editable(self):
        doc = Record(project="PROJECT", customer="CUSTOMER", service_person_name="Old technician",
                     previous=Record(project="PROJECT", service_person_name="Old technician"))
        pms_visit.PMSVisit.validate(doc)

    def test_project_values_endpoint_requires_pms_access(self):
        self.frappe.has_permission.return_value = False
        with self.assertRaises(ValueError):
            unwrap(pms_visit.get_project_values)("PROJECT")
        self.frappe.get_doc.assert_not_called()

    def test_schema_retains_legacy_fields_and_matches_site_visit_document_permissions(self):
        folder = Path(__file__).parent
        schema = json.loads((folder / "pms_visit.json").read_text())
        fields = {df["fieldname"]: df for df in schema["fields"]}
        self.assertTrue(set(migrate_pms.LEGACY_FIELDS) <= set(fields))
        self.assertEqual(fields["plant_capacity_kw"]["fieldtype"], "Float")
        self.assertFalse(fields["client_name"].get("reqd"))
        self.assertEqual(fields["client_name"]["depends_on"], "eval:!doc.customer")
        self.assertEqual(fields["client_name"]["mandatory_depends_on"], "eval:!doc.customer")
        self.assertLess(schema["field_order"].index("customer"), schema["field_order"].index("client_name"))
        self.assertEqual((fields["service_person"]["fieldtype"], fields["service_person"]["options"]), ("Link", "Employee"))
        self.assertEqual(fields["service_person_name"]["fieldtype"], "Data")
        self.assertEqual(fields["project"]["mandatory_depends_on"], "eval:!doc.legacy_site_data_collection")
        site_visit = json.loads((folder.parent / "site_visit/site_visit.json").read_text())
        self.assertEqual(schema["permissions"], [row for row in site_visit["permissions"] if not row.get("permlevel")])


class TestLegacyPMSMigration(unittest.TestCase):
    def setUp(self):
        mock = patch.object(migrate_pms, "frappe")
        self.frappe = mock.start()
        self.addCleanup(mock.stop)
        self.frappe.flags = frappe._dict()
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.row = Record(name="Old client-Place-10/26-01", client_name="Old client", service_person_name="Old technician", plant_capacity_kw=8.5,
                          owner="Administrator", creation="2026-10-14", modified="2026-10-20", modified_by="Administrator")
        self.frappe.get_all.return_value = [self.row]
        self.frappe.db.exists.side_effect = lambda dt, name: dt == "DocType"
        self.frappe.get_meta.return_value.has_field.return_value = True
        self.frappe.get_meta.return_value.fields = []
        files = patch.object(migrate_pms, "attachments_for", return_value=[])
        files.start()
        self.addCleanup(files.stop)

    def test_preview_is_read_only_by_default(self):
        result = migrate_pms.migrate()
        self.assertEqual(result["ready"], 1)
        self.assertEqual(result["copied"], 0)
        self.frappe.get_doc.assert_not_called()
        self.frappe.db.set_value.assert_not_called()
        self.frappe.db.savepoint.assert_not_called()

    def test_copy_preserves_names_fields_and_audit_dates_without_deleting_source(self):
        visit = self.frappe.get_doc.return_value
        visit.name = self.row.name
        result = migrate_pms.migrate(dry_run=False)
        values = self.frappe.get_doc.call_args.args[0]
        self.assertEqual(values["client_name"], "Old client")
        self.assertEqual(values["plant_capacity_kw"], 8.5)
        self.assertNotIn("project", values)
        self.assertEqual(values["legacy_site_data_collection"], self.row.name)
        visit.insert.assert_called_once_with(ignore_permissions=True, ignore_mandatory=True, set_name=self.row.name)
        self.assertEqual(result["copied"], 1)
        self.assertFalse(self.frappe.flags.in_legacy_pms_import)
        self.frappe.db.set_value.assert_called_once_with("PMS Visit", self.row.name,
            {field: self.row.get(field) for field in migrate_pms.AUDIT_FIELDS}, update_modified=False)
        self.frappe.delete_doc.assert_not_called()

    def test_copy_is_idempotent(self):
        self.frappe.db.exists.side_effect = lambda dt, name: dt == "DocType" or isinstance(name, dict)
        result = migrate_pms.migrate(dry_run=False)
        self.assertEqual(result["already_copied"], 1)
        self.assertEqual(result["copied"], 0)
        self.frappe.get_doc.assert_not_called()

    def test_name_conflict_stops_copy(self):
        self.frappe.db.exists.side_effect = lambda dt, name: dt == "DocType" or isinstance(name, str)
        with self.assertRaisesRegex(ValueError, "preflight failed"):
            migrate_pms.migrate(dry_run=False)
        self.frappe.get_doc.assert_not_called()

    def test_failure_rolls_back_and_restores_import_context(self):
        self.frappe.get_doc.return_value.insert.side_effect = RuntimeError("failed insert")
        with self.assertRaises(RuntimeError):
            migrate_pms.migrate(dry_run=False)
        self.frappe.db.rollback.assert_called_once_with(save_point="legacy_pms_copy")
        self.assertFalse(self.frappe.flags.in_legacy_pms_import)

    def test_attachment_error_prevents_all_copies(self):
        self.frappe.get_all.return_value = [self.row, Record(self.row, name="BROKEN")]
        with patch.object(migrate_pms, "attachments_for", side_effect=[[], ValueError("Missing image")]):
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                migrate_pms.migrate(dry_run=False)
        self.frappe.get_doc.assert_not_called()
        self.frappe.db.savepoint.assert_not_called()

    def test_each_photo_field_gets_its_own_reference_without_moving_original(self):
        url = "/private/files/photo.png"
        self.row.update(panel_image=url, house_image=url)
        source_file = MagicMock(file_url=url)
        self.frappe.get_doc.return_value.name = self.row.name
        with patch.object(migrate_pms, "attachments_for", return_value=[source_file]):
            migrate_pms.migrate(dry_run=False)
        self.assertEqual(self.frappe.copy_doc.call_count, 2)
        updates = self.frappe.copy_doc.return_value.update.call_args_list
        self.assertEqual([call.args[0]["attached_to_field"] for call in updates], ["panel_image", "house_image"])
        self.assertTrue(self.frappe.copy_doc.return_value.flags.copy_from_existing_file)
        source_file.update.assert_not_called()

    def test_missing_source_is_a_no_op(self):
        self.frappe.db.exists.side_effect = None
        self.frappe.db.exists.return_value = False
        result = migrate_pms.migrate()
        self.assertEqual(result["source_total"], 0)
        self.frappe.get_all.assert_not_called()

    def test_preview_checks_conditional_client_and_historical_service_name(self):
        for field in ("client_name", "service_person_name"):
            with self.subTest(field=field):
                row = Record(self.row)
                row[field] = "  "
                self.frappe.get_all.return_value = [row]
                result = migrate_pms.migrate()
                self.assertEqual(result["ready"], 0)
                self.assertIn(field, result["errors"][0]["reason"])

    def test_preview_accepts_customer_without_client_name(self):
        self.row.update(customer="CUSTOMER", client_name=None)
        self.assertEqual(migrate_pms.migrate()["ready"], 1)
