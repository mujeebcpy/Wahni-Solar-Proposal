"""Report worker outputs, omissions, failure handling and permissions."""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from pypdf import PdfWriter

from wahni_solar.solar_project import api
from wahni_solar.solar_project.constants import AGREEMENT_SECTIONS, PANEL_DOCUMENT, SECTIONS
from wahni_solar.solar_project.documents import pdf_bytes, read_pdf
from wahni_solar.solar_project.tests.helpers import Record, TEMPLATES


class TestReportGeneration(unittest.TestCase):
    def setUp(self):
        self.report = Record(name="REPORT-1", project="PROJECT-1", requested_by="report-user",
                             status="Queued", input_snapshot="/private/files/inputs.zip")
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
        self.frappe.db.get_value.return_value = 1
        self.frappe.throw.side_effect = frappe.ValidationError
        for mock in (
            patch.object(api, "frappe", self.frappe),
            patch.object(api, "read_file", side_effect=lambda url: (self.inputs[url], {})),
            patch.object(api, "save_file", side_effect=self.save_file),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def get_doc(self, doctype, name):
        if doctype == "Project Report":
            return self.report
        return self.records.get((doctype, name), Record(name=name))

    def save_file(self, filename, content, doctype, name, **kwargs):
        self.outputs[filename] = content
        return Record(file_url=f"/private/files/{filename}")

    def add_source(self, category, content, origin="Library", **metadata):
        source = next((row for row in self.context["sources"] if row["category"] == category), None)
        if source is None:
            source = {"category": category}
            self.context["sources"].append(source)
        url = f"/files/{category}"
        source.update(url=url, origin=origin, doctype="Project Report Document", name=category, **metadata)
        self.inputs[url] = content

    def generate(self, legacy=False):
        snapshot = api._snapshot(self.context)
        if legacy:
            from io import BytesIO
            from zipfile import ZipFile
            output = BytesIO()
            with ZipFile(BytesIO(snapshot)) as old, ZipFile(output, "w") as new:
                for name in old.namelist():
                    content = old.read(name)
                    if name == "context.json":
                        context = json.loads(content)
                        context.pop("snapshot_version", None)
                        content = json.dumps(context).encode()
                    new.writestr(name, content)
            snapshot = output.getvalue()
        self.inputs[self.report.input_snapshot] = snapshot
        api.build_report(self.report.name)
        return json.loads(self.report.result)

    def test_legacy_queued_report_generates_sld_and_excludes_agreements(self):
        for category, filename in {
            "Check List": "Check_List_Fillable.pdf",
            "Project Completion Report": "Completion_Certificate_Fillable.pdf",
            "SLD Template": "SLD_Enphase.qet",
            "KSEB Agreement": "KSEB_Agreement_Fillable.pdf",
            "Customer Vendor Agreement": "Solar_Customer_Vendor_Agreement_Fillable.pdf",
        }.items():
            self.add_source(category, (TEMPLATES / filename).read_bytes())

        result = self.generate(legacy=True)

        self.assertEqual(set(self.outputs), {"REPORT-1-SLD.qet", "REPORT-1-Project-Report.pdf"})
        self.assertEqual(self.report.sld_qet, "/private/files/REPORT-1-SLD.qet")
        categories = {row["category"] for row in result["included"] + result["omitted"]}
        self.assertFalse(set(AGREEMENT_SECTIONS) & categories)
        self.assertFalse(set(AGREEMENT_SECTIONS) & result["missing_fields"].keys())
        self.assertFalse(any(category in warning for category in AGREEMENT_SECTIONS for warning in result["warnings"]))
        reader = read_pdf(self.outputs["REPORT-1-Project-Report.pdf"])
        self.assertEqual(len(reader.pages), 3)
        fields = reader.get_fields()
        self.assertEqual(fields["section_00.solar_plant_owner"]["/V"], "Test Customer")
        self.assertEqual(fields["section_01.customer_name"]["/V"], "Test Customer")
        for call in api.save_file.call_args_list:
            self.assertEqual(call.args[2:], ("Project", "PROJECT-1"))
            self.assertEqual(call.kwargs["is_private"], 1)

    def test_project_upload_is_preserved_in_report(self):
        original = (TEMPLATES / "Completion_Certificate_Fillable.pdf").read_bytes()
        self.add_source("Project Completion Report", original, origin="Project upload")

        result = self.generate()

        self.assertEqual(self.report.status, "Completed with omissions")
        self.assertEqual([row["category"] for row in result["included"]], ["Project Completion Report"])
        self.assertFalse({"Cover Page", "End Page", "Sales Invoice"} & {row["category"] for row in result["omitted"]})
        fields = read_pdf(self.outputs["REPORT-1-Project-Report.pdf"]).get_fields()
        self.assertEqual(fields["section_00.customer_name"]["/V"], read_pdf(original).get_fields()["customer_name"]["/V"])

    def test_combined_panel_pdf_is_included_once(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=200, height=200)
        self.add_source(PANEL_DOCUMENT, pdf_bytes(writer), brand="Adani", panel_watt_peak=630)

        result = self.generate()

        self.assertEqual([row["category"] for row in result["included"]], [PANEL_DOCUMENT])
        self.assertEqual(len(read_pdf(self.outputs["REPORT-1-Project-Report.pdf"]).pages), 2)
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
        self.frappe.set_user.assert_called_with("worker-user")

    def test_worker_rechecks_project_write_permission(self):
        self.records[("Project", "PROJECT-1")] = Record(name="PROJECT-1", denied=True)

        self.generate()

        self.assertEqual(self.report.status, "Failed")
        self.assertEqual(self.outputs, {})
        self.frappe.set_user.assert_called_with("worker-user")

    def test_finished_report_is_not_generated_again(self):
        self.report.status = "Completed"

        api.build_report(self.report.name)

        api.read_file.assert_not_called()
        api.save_file.assert_not_called()

    def test_new_snapshot_never_fills_forms_and_freezes_native_pdf(self):
        writer = PdfWriter()
        writer.add_blank_page(width=321, height=456)
        original = pdf_bytes(writer)
        source = next(row for row in self.context["sources"] if row["category"] == "Check List")
        source.update(document_type="Solar Installation Checklist", doctype="Solar Installation Checklist",
                      name="CHECK-1", origin="Print Format")
        resolved = {"values": {"consumer_number": "old"}, "missing_fields": [], "warnings": [], "sources": []}
        with patch.object(api, "render_document", return_value=(original, resolved)) as render, \
                patch.object(api, "fill_form") as fill:
            self.inputs[self.report.input_snapshot] = api._snapshot(self.context)
            self.context["grid"]["consumer_no"] = "new"
            api.build_report(self.report.name)
        render.assert_called_once()
        fill.assert_not_called()
        pdf = read_pdf(self.outputs["REPORT-1-Project-Report.pdf"])
        self.assertEqual(float(pdf.pages[0].mediabox.width), 321)
        self.assertFalse(pdf.get_fields())
