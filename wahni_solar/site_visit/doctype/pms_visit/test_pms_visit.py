import json
import re
import unittest
from inspect import unwrap
from pathlib import Path
from unittest.mock import patch

import frappe

from wahni_solar.site_visit.doctype.pms_visit import pms_visit


class Record(frappe._dict):
    def __init__(self, **values):
        super().__init__({"status": "Assigned", **values})

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
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.get_doc.return_value = Record(status="Completed", customer="CUSTOMER", check_permission=lambda permission: None)
        eligible = patch.object(pms_visit, "is_eligible_supervisor", return_value=True)
        self.eligible = eligible.start()
        self.addCleanup(eligible.stop)

    def valid_record(self, **values):
        return Record(project="PROJECT", customer="CUSTOMER", service_person="EMPLOYEE", **values)

    def completed_record(self, **values):
        fields = {field: "Present" for field in pms_visit.COMPLETION_FIELDS}
        fields.update({"plant_capacity_kw": 5, "status": "Completed", **values})
        return self.valid_record(**fields)

    def test_assignment_and_progress_allow_incomplete_inspection(self):
        for status in ("Assigned", "In Progress"):
            with self.subTest(status=status):
                pms_visit.PMSVisit.validate(self.valid_record(status=status))
        self.frappe.only_for.assert_not_called()

    def test_completion_requires_every_inspection_field(self):
        for field, label in pms_visit.COMPLETION_FIELDS.items():
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, re.escape(label)):
                pms_visit.PMSVisit.validate(self.completed_record(**{field: None}))

    def test_completion_rejects_whitespace_details(self):
        with self.assertRaisesRegex(ValueError, "Inspection Remarks"):
            pms_visit.PMSVisit.validate(self.completed_record(inspection_remarks="  \n "))

    def test_complete_report_can_be_saved(self):
        pms_visit.PMSVisit.validate(self.completed_record())
        self.frappe.only_for.assert_called_once_with(("System Manager", "Project Supervisor"))

    def test_completion_checks_role(self):
        self.frappe.only_for.side_effect = frappe.PermissionError
        with self.assertRaises(frappe.PermissionError):
            pms_visit.PMSVisit.validate(self.completed_record())

    def test_completion_rechecks_employee_eligibility(self):
        self.eligible.return_value = False
        previous = self.valid_record(service_person_name="Technician")
        with self.assertRaisesRegex(ValueError, "Project Supervisor role"):
            pms_visit.PMSVisit.validate(self.completed_record(previous=previous))

    def test_completed_history_preserves_inactive_employee(self):
        self.eligible.return_value = False
        previous = self.completed_record(service_person_name="Technician")
        pms_visit.PMSVisit.validate(self.completed_record(previous=previous))
        self.eligible.assert_not_called()
        self.frappe.only_for.assert_not_called()

    def test_completed_report_cannot_lose_required_details(self):
        previous = self.completed_record()
        with self.assertRaisesRegex(ValueError, "Panel Image"):
            pms_visit.PMSVisit.validate(self.completed_record(previous=previous, panel_image=None))

    def test_invalid_status_is_rejected(self):
        for status in ("Draft", "Other", None):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "valid PMS Visit status"):
                pms_visit.PMSVisit.validate(self.valid_record(status=status))

    def test_new_visit_requires_project(self):
        with self.assertRaisesRegex(ValueError, "Project is required"):
            pms_visit.PMSVisit.validate(Record())

    def test_new_visit_cannot_claim_an_existing_uat_exception(self):
        with self.assertRaisesRegex(ValueError, "cannot have a legacy report reference"):
            pms_visit.PMSVisit.validate(Record(legacy_site_data_collection="OLD"))

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

    def test_schema_matches_current_form_and_site_visit_document_permissions(self):
        folder = Path(__file__).parent
        schema = json.loads((folder / "pms_visit.json").read_text())
        fields = {df["fieldname"]: df for df in schema["fields"]}
        self.assertEqual(set(schema["field_order"]), set(fields))
        self.assertEqual(len(schema["field_order"]), len(fields))
        self.assertEqual(fields["status"]["default"], "Assigned")
        self.assertEqual(fields["status"]["options"], "Assigned\nIn Progress\nCompleted")
        self.assertTrue(fields["status"]["no_copy"])
        self.assertEqual([state["title"] for state in schema["states"]], ["Assigned", "In Progress", "Completed"])
        for field in pms_visit.COMPLETION_FIELDS:
            self.assertFalse(fields[field].get("reqd"))
            self.assertEqual(fields[field]["mandatory_depends_on"], "eval:doc.status == 'Completed'")
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
