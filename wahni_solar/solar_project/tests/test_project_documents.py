"""Automatic records, live values, default preservation and Project permissions."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from jinja2 import Environment

from wahni_solar.solar_project import project_documents as documents
from wahni_solar.solar_project import sources
from wahni_solar.solar_project.tests.helpers import Record

BASE = Path(__file__).resolve().parents[1]


def document(doctype, **values):
    slug = doctype.lower().replace(" ", "_")
    schema = json.loads((BASE / "doctype" / slug / f"{slug}.json").read_text())
    fields = [Record(field) for field in schema["fields"]]
    return Record(doctype=doctype, name="DOC-1", project="PROJECT-1", meta=Record(fields=fields), **values)


class TestProjectDocuments(unittest.TestCase):
    def test_automatic_creation_reuses_all_four_records_and_never_resets_edits(self):
        fake = MagicMock()
        stored = {}
        fake.get_doc.side_effect = lambda dt, name: Record(name=name) if dt == "Project" else stored[dt]
        fake.db.get_value.side_effect = lambda dt, filters, field, **kwargs: stored[dt].name if dt in stored else None

        def new_doc(doctype):
            doc = MagicMock()
            doc.doctype, doc.name = doctype, "DOC-1"
            doc.insert.side_effect = lambda **kwargs: stored.setdefault(doctype, doc)
            return doc

        fake.new_doc.side_effect = new_doc
        with patch.object(documents, "frappe", fake):
            first = documents.ensure_documents("PROJECT-1")
            first["Project Completion Report"].electrical_inspector_approval_reference = ""
            second = documents.ensure_documents("PROJECT-1")
        self.assertEqual(len(stored), 4)
        self.assertEqual(fake.new_doc.call_count, 4)
        self.assertTrue(all(call.kwargs.get("for_update") for call in fake.db.get_value.call_args_list))
        self.assertEqual(second["Project Completion Report"].electrical_inspector_approval_reference, "")
        self.assertEqual(fake.db.sql.call_count, 2)
        self.assertIn("FOR UPDATE", fake.db.sql.call_args.args[0])
        for doc in stored.values():
            doc.insert.assert_called_once_with(ignore_permissions=True)
            doc.save.assert_not_called()

    def test_project_write_permission_is_required_before_creation(self):
        with patch.object(documents, "frappe") as fake:
            fake.get_doc.return_value.check_permission.side_effect = frappe.PermissionError
            with self.assertRaises(frappe.PermissionError):
                documents.ensure_documents("PROJECT-1")
            fake.new_doc.assert_not_called()
            fake.db.sql.assert_not_called()

    def test_live_sources_change_without_overwriting_saved_dates_or_defaults(self):
        doc = document("Customer Vendor Agreement", agreement_date="2026-10-01", vendor_signatory="", module_efficiency="20%")
        context = {"customer": {"customer_name": "Old Name"}, "proposal": {"capacity_kw": 5, "project_cost": 300000},
                   "warnings": [], "permissions": []}
        with patch.object(documents.frappe, "get_doc", return_value=Record(name="PROJECT-1")), \
                patch.object(sources, "resolve_context", return_value=context) as resolve:
            old = documents.resolve_print_context(doc)
            context["customer"]["customer_name"] = "Updated Name"
            context["proposal"]["capacity_kw"] = 6
            new = documents.resolve_print_context(doc)
        self.assertEqual(old["values"]["name"], "Old Name")
        self.assertEqual(new["values"]["name"], "Updated Name")
        self.assertEqual(new["values"]["system_capacity"], "6kW")
        self.assertEqual(new["values"]["date"], "01-10-2026")
        self.assertEqual(new["values"]["vendor_signatory"], "")
        self.assertEqual(new["values"]["module_efficiency"], "20%")
        self.assertNotIn("capacity_kw", doc)
        resolve.assert_called_with("PROJECT-1", categories=("Customer Vendor Agreement",), include_sources=False)

    def test_voltage_uses_grid_phase_and_capacity_uses_grid_for_checklist(self):
        doc = document("Solar Installation Checklist", supply_voltage="230 V", inverter_serial_numbers="SERIAL-1")
        context = {"grid": {"phase": "Three Phase", "proposed_solar_capacity": 5},
                   "proposal": {"capacity_kw": 6}, "package": {"brand": "Enphase", "connection_type": "Single Phase"},
                   "panel": {"custom_panel_watt_peak": 630}, "inverter": {"custom_rated_capacity": 5},
                   "warnings": [], "permissions": []}
        with patch.object(documents.frappe, "get_doc", return_value=Record()), \
                patch.object(sources, "resolve_context", return_value=context):
            values = documents.resolve_print_context(doc)["values"]
        self.assertEqual(values["plant_total_capacity"], "5kW")
        self.assertEqual(values["voltage_and_number_of_phase"], "230 V, 3 Phase")
        self.assertEqual(values["plant_individual_capacity"], "630 Wp")
        self.assertEqual(values["inverter_make_and_serial_number"], "Enphase\nSERIAL-1")

    def test_each_type_has_unique_project_link_and_no_copied_customer_or_capacity_fields(self):
        for doctype in documents.DOCUMENT_TYPES.values():
            doc = document(doctype)
            fields = {field.fieldname: field for field in doc.meta.fields}
            self.assertEqual(fields["project"].options, "Project")
            self.assertEqual(fields["project"].unique, 1)
            self.assertEqual(fields["project"].reqd, 1)
            self.assertFalse({"customer", "customer_name", "customer_address", "capacity_kw", "connection_type", "project_cost", "solar_proposal", "grid_check"} & fields.keys())
            for field in fields.values():
                if "resistance" in field.fieldname or "serial" in field.fieldname:
                    self.assertFalse(field.get("default"))

    def test_permission_checks_follow_project_for_read_and_write(self):
        doc = Record(project="P")
        with patch.object(documents.frappe, "has_permission", return_value=False) as permission:
            self.assertFalse(documents.has_document_permission(doc, "print", "user"))
            permission.assert_called_with("Project", "read", "P", user="user")
            self.assertFalse(documents.has_document_permission(doc, "write", "user"))
            permission.assert_called_with("Project", "write", "P", user="user")

    def test_formats_escape_user_values_and_match_document_types(self):
        malicious = '<script>alert("x")</script>'
        for doctype in documents.DOCUMENT_TYPES.values():
            slug = doctype.lower().replace(" ", "_")
            fmt = json.loads((BASE / "print_format" / slug / f"{slug}.json").read_text())
            doc = document(doctype)
            values = {field.fieldname: malicious for field in doc.meta.fields}
            values.update(name=malicious, customer_name=malicious, installation_owner_name=malicious)
            doc.print_context = {"values": values}
            rendered = Environment().from_string(fmt["html"]).render(doc=doc)
            self.assertNotIn("<script>", rendered)
            self.assertIn("&lt;script&gt;", rendered)
            self.assertEqual(fmt["doc_type"], doctype)
