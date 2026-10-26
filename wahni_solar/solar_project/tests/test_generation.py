"""Report worker outputs (cached, never attached), omissions, failures and permissions."""

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
from pypdf import PdfWriter

from wahni_solar.solar_project import api
from wahni_solar.solar_project.constants import AGREEMENT_SECTIONS, PANEL_DOCUMENT, REPORT_OUTPUT_SECONDS, SECTIONS
from wahni_solar.solar_project.project_documents import DOCUMENT_TYPES
from wahni_solar.solar_project.documents import pdf_bytes, read_pdf
from wahni_solar.solar_project.tests.helpers import Record, TEMPLATES


class TestReportGeneration(unittest.TestCase):
    def setUp(self):
        self.report = Record(name="REPORT-1", project="PROJECT-1", requested_by="report-user", status="Running")
        self.context = {
            "sources": [{"category": category, "reason": "No document available."}
                        for category in (*SECTIONS, "SLD Template")],
            "permissions": [], "warnings": [],
            "grid": {"consumer_name": "Test Customer", "consumer_no": "1234567890123",
                     "registered_mobile": "9000000000", "customer_address": "Thrissur",
                     "phase": "Single Phase"},
            "proposal": {"capacity_kw": 5},
            "package": {"connection_type": "Single Phase"},
        }
        self.inputs = {}
        self.outputs = {}
        self.records = {}
        self.frappe = MagicMock()
        self.frappe.session.user = "worker-user"
        self.frappe.get_doc.side_effect = self.get_doc
        # An existing Project Report is updated in place.
        self.frappe.db.get_value.return_value = "REPORT-1"
        self.frappe.throw.side_effect = frappe.ValidationError
        self.frappe.cache.set_value.side_effect = self.save_output
        self.frappe.cache.exists.side_effect = lambda key: key in self.cached
        self.cached = {}
        for mock in (
            patch.object(api, "frappe", self.frappe),
            patch.object(api, "read_file", side_effect=lambda url: (self.inputs[url], {})),
            patch.object(api, "now_datetime", return_value=datetime(2026, 10, 26, 12)),
            patch.object(api, "resolve_context", side_effect=lambda project: self.context),
            patch.object(api, "get_document", side_effect=lambda project, category: Record(
                doctype=DOCUMENT_TYPES[category], name=None, project=project)),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def get_doc(self, doctype, name=None):
        if doctype == "Project Report":
            return self.report
        if isinstance(doctype, dict):
            request = MagicMock()
            request.insert.return_value = self.report
            return request
        return self.records.get((doctype, name), Record(name=name))

    def save_output(self, key, content, expires_in_sec=None):
        self.assertEqual(expires_in_sec, REPORT_OUTPUT_SECONDS)
        self.cached[key] = content
        self.outputs[key.rsplit(":", 1)[-1]] = content

    def add_source(self, category, content, origin="Library", **metadata):
        source = next((row for row in self.context["sources"] if row["category"] == category), None)
        if source is None:
            source = {"category": category}
            self.context["sources"].append(source)
        url = f"/files/{category}"
        source.update(url=url, origin=origin, doctype="Project Report Document", name=category, **metadata)
        self.inputs[url] = content

    def generate(self):
        api.generate_project_report("PROJECT-1")
        return json.loads(self.report.get("result") or "{}")

    def test_report_generates_sld_and_excludes_agreements_without_attachments(self):
        for category, filename in {
            "Project Completion Report": "Completion_Certificate_Fillable.pdf",
            "SLD Template": "SLD_Enphase.qet",
            "KSEB Agreement": "KSEB_Agreement_Fillable.pdf",
            "Customer Vendor Agreement": "Solar_Customer_Vendor_Agreement_Fillable.pdf",
        }.items():
            self.add_source(category, (TEMPLATES / filename).read_bytes(), origin="Project upload")

        result = self.generate()

        self.assertEqual(set(self.outputs), {"qet", "pdf"})
        self.assertEqual(result["outputs"], ["qet", "pdf"])
        self.assertIn(b"Test Customer", self.outputs["qet"])
        self.assertEqual(self.report.available_until, datetime(2026, 10, 26, 18))
        categories = {row["category"] for row in result["included"] + result["omitted"]}
        self.assertFalse(set(AGREEMENT_SECTIONS) & categories)
        self.assertFalse(set(AGREEMENT_SECTIONS) & result["missing_fields"].keys())
        self.assertFalse(any(category in warning for category in AGREEMENT_SECTIONS for warning in result["warnings"]))
        self.assertEqual(len(read_pdf(self.outputs["pdf"]).pages), 1)
        self.frappe.get_attr.assert_not_called()

    def test_project_upload_is_preserved_in_report(self):
        original = (TEMPLATES / "Completion_Certificate_Fillable.pdf").read_bytes()
        self.add_source("Project Completion Report", original, origin="Project upload")

        result = self.generate()

        self.assertEqual(self.report.status, "Completed with omissions")
        self.assertEqual([row["category"] for row in result["included"]], ["Project Completion Report"])
        self.assertFalse({"Cover Page", "End Page", "Sales Invoice"} & {row["category"] for row in result["omitted"]})
        fields = read_pdf(self.outputs["pdf"]).get_fields()
        self.assertEqual(fields["section_00.customer_name"]["/V"], read_pdf(original).get_fields()["customer_name"]["/V"])

    def test_combined_panel_pdf_is_included_once(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=200, height=200)
        self.add_source(PANEL_DOCUMENT, pdf_bytes(writer), brand="Adani", panel_watt_peak=630)

        result = self.generate()

        self.assertEqual([row["category"] for row in result["included"]], [PANEL_DOCUMENT])
        self.assertEqual(len(read_pdf(self.outputs["pdf"]).pages), 2)
        self.assertEqual(result["sources"][0]["panel_watt_peak"], 630)

    def test_complete_report_has_all_sections_in_order(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        pdf = pdf_bytes(writer)
        for category in SECTIONS:
            self.add_source(category, pdf, origin="Project upload")
        self.add_source("SLD Template", (TEMPLATES / "SLD_Enphase.qet").read_bytes())

        result = self.generate()

        self.assertEqual(self.report.status, "Completed")
        self.assertEqual(self.report.progress, 100)
        self.assertEqual([row["category"] for row in result["included"]], list(SECTIONS))
        self.assertEqual(result["omitted"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["missing_fields"], {})

    def test_no_usable_pdfs_marks_report_failed(self):
        self.generate()

        self.assertEqual(self.report.status, "Failed")
        self.assertIn("No usable PDFs", self.report.message)
        self.assertEqual(self.outputs, {})

    def test_generation_requires_project_write_permission(self):
        self.records[("Project", "PROJECT-1")] = Record(name="PROJECT-1", denied=True)

        with self.assertRaises(frappe.PermissionError):
            self.generate()

        api.read_file.assert_not_called()
        self.frappe.cache.set_value.assert_not_called()

    def test_native_documents_use_the_projects_record(self):
        writer = PdfWriter()
        writer.add_blank_page(width=321, height=456)
        original = pdf_bytes(writer)
        source = next(row for row in self.context["sources"] if row["category"] == "Check List")
        source.update(document_type="Solar Installation Checklist", origin="Print Format")
        resolved = {"values": {"consumer_number": "new"}, "missing_fields": ["tariff"], "warnings": [], "sources": []}
        with patch.object(api, "render_document", return_value=(original, resolved)) as render:
            result = self.generate()
        self.assertEqual(render.call_args.args[0].doctype, "Solar Installation Checklist")
        api.get_document.assert_called_once_with("PROJECT-1", "Check List")
        self.assertEqual(result["missing_fields"]["Check List"], ["tariff"])
        pdf = read_pdf(self.outputs["pdf"])
        self.assertEqual(float(pdf.pages[0].mediabox.width), 321)
        self.assertFalse(pdf.get_fields())

    def test_regeneration_updates_the_single_project_report(self):
        self.add_source("End Page", pdf_bytes(self.blank_writer()), origin="Project upload")
        self.report.update(status="Failed", result="old", message="old")

        self.generate()

        self.frappe.get_doc.assert_any_call("Project Report", "REPORT-1")
        self.assertFalse(any(isinstance(call.args[0], dict) for call in self.frappe.get_doc.call_args_list))
        self.assertEqual(self.report.status, "Completed with omissions")
        self.assertEqual(self.report.requested_by, "worker-user")
        self.frappe.cache.delete_value.assert_any_call("wahni_solar:project_report:REPORT-1:pdf")

    def blank_writer(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        return writer

    def test_failed_report_discards_cached_outputs(self):
        self.add_source("SLD Template", (TEMPLATES / "SLD_Enphase.qet").read_bytes())

        self.generate()

        self.assertEqual(self.report.status, "Failed")
        self.frappe.cache.delete_value.assert_any_call("wahni_solar:project_report:REPORT-1:qet")
