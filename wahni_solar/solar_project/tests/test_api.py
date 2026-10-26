"""Generation requests, on-demand annexures and downloads."""

import base64
import hashlib
import unittest
from inspect import unwrap
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.solar_project import api
from wahni_solar.solar_project.constants import AGREEMENT_SECTIONS
from wahni_solar.solar_project.tests.helpers import Record


class TestReportAPI(unittest.TestCase):
    def grid(self, **values):
        return Record({"doctype": "KSEB Grid Check", "name": "G", "consumer_name": "C", "consumer_no": "1",
                       "proposed_solar_capacity": 3, **values})

    def test_annexures_are_rendered_without_saving_on_grid_check(self):
        grid = self.grid()
        with patch.object(api, "frappe") as fake:
            fake.get_doc.return_value = grid
            fake.get_print.return_value = b"annexure"
            for number in (1, 2, 3):
                self.assertEqual(api._render_annexure("G", number), b"annexure")
                self.assertEqual(fake.get_print.call_args.kwargs["print_format"], f"KSEB Annexure {'I' * number}")
        fake.get_all.assert_not_called()
        fake.get_attr.assert_not_called()

    def test_annexure_rendering_requires_grid_access_and_details(self):
        with patch.object(api, "frappe") as fake:
            fake.get_doc.return_value = self.grid(denied=True)
            with self.assertRaises(frappe.PermissionError):
                api._render_annexure("G", 1)
            fake.get_doc.return_value = self.grid(consumer_no=None)
            with self.assertRaisesRegex(ValueError, "Consumer Number"):
                api._render_annexure("G", 1)
            fake.get_print.assert_not_called()

    def test_rendering_generates_annexures_and_records_failures(self):
        context = {"warnings": [], "sources": [
            {"category": "Annexure I", "url": "/files/existing.pdf", "origin": "Project upload"},
            {"category": "Annexure II", "name": "G", "annexure_number": 2},
            {"category": "Annexure III", "name": "G", "annexure_number": 3},
        ]}
        with patch.object(api, "_render_annexure", side_effect=[b"new", ValueError("Solar capacity is missing")]) as render, \
                patch.object(api, "read_file", side_effect=lambda url: (url.encode(), {})):
            contents = api._render_sources("P", context)
        self.assertEqual([call.args for call in render.call_args_list], [("G", 2), ("G", 3)])
        self.assertEqual(contents, {"Annexure I": b"/files/existing.pdf", "Annexure II": b"new"})
        self.assertIn("Solar capacity is missing", context["sources"][2]["reason"])
        self.assertEqual(context["sources"][1]["sha256"], hashlib.sha256(b"new").hexdigest())

    def test_missing_invoice_is_not_rendered(self):
        context = {"warnings": [], "sources": [{"category": "Sales Invoice", "reason": "No document available."}]}
        with patch.object(api.frappe, "get_print") as render:
            self.assertEqual(api._render_sources("P", context), {})
            render.assert_not_called()

    def test_unreadable_file_does_not_prevent_other_documents(self):
        context = {"warnings": [], "sources": [{"category": "Cover Page", "url": "/files/a.pdf"},
                                               {"category": "End Page", "url": "/files/b.pdf"}]}
        with patch.object(api, "read_file", side_effect=[ValueError("bad file"), (b"good", {})]):
            contents = api._render_sources("P", context)
        self.assertIn("bad file", context["sources"][0]["reason"])
        self.assertEqual(contents, {"End Page": b"good"})

    def test_project_upload_categories_cannot_repeat(self):
        doc = Record(custom_report_attachments=[Record(category="Cover Page", file=None),
                                               Record(category="Cover Page", file=None)])
        with patch.object(api.frappe, "throw", side_effect=ValueError("duplicate")):
            with self.assertRaises(ValueError):
                api.validate_project(doc)

    def test_generation_requires_project_write_permission(self):
        project = MagicMock()
        project.check_permission.side_effect = frappe.PermissionError
        with patch.object(api.frappe, "get_doc", return_value=project), patch.object(api, "resolve_context") as resolve, \
                patch.object(frappe.local, "flags", frappe._dict(in_test=True), create=True):
            with self.assertRaises(frappe.PermissionError):
                api.generate_project_report("PROJECT-1")
            project.check_permission.assert_called_once_with("write")
            resolve.assert_not_called()

    def test_project_panel_item_must_belong_to_panel_group(self):
        doc = Record(custom_panel_item="ITEM", custom_report_attachments=[])
        for group in ("Panel", "Microinverters", None):
            with self.subTest(group=group), patch.object(api, "frappe") as fake:
                fake.db.get_value.return_value = group
                fake.throw.side_effect = ValueError
                if group == "Panel":
                    api.validate_project(doc)
                else:
                    with self.assertRaises(ValueError):
                        api.validate_project(doc)
                fake.db.get_value.assert_called_once_with("Item", "ITEM", "item_group")

    def test_report_download_requires_read_permission_and_cached_output(self):
        response = frappe._dict()
        with patch.object(api, "frappe") as fake:
            fake.local.response = response
            fake.throw.side_effect = lambda message: (_ for _ in ()).throw(ValueError(message))
            fake.get_doc.return_value = Record(name="R", project="P")
            fake.cache.get_value.return_value = b"%PDF"
            api.download_project_report("R", "pdf")
            self.assertEqual((response.filename, response.filecontent, response.type), ("P-Project-Report.pdf", b"%PDF", "pdf"))
            fake.cache.get_value.return_value = None
            with self.assertRaisesRegex(ValueError, "no longer available"):
                api.download_project_report("R", "qet")
            with self.assertRaises(ValueError):
                api.download_project_report("R", "zip")
            fake.get_doc.return_value = Record(name="R", project="P", denied=True)
            with self.assertRaises(frappe.PermissionError):
                api.download_project_report("R", "pdf")

    def test_standalone_outputs_use_mapped_formats_or_explicit_overrides(self):
        from wahni_solar.solar_project.project_documents import DOCUMENT_TYPES
        for category, doctype in DOCUMENT_TYPES.items():
            record = Record(doctype=doctype, name="D", project="P")
            context = {"sources": [{"category": category, "document_type": doctype}], "warnings": []}
            with self.subTest(category=category), patch.object(api, "frappe") as fake, \
                    patch.object(api, "get_document", return_value=record) as get_document, \
                    patch.object(api, "resolve_context", return_value=context), \
                    patch.object(api, "render_document", return_value=(b"native-pdf", {"missing_fields": [], "warnings": []})) as render:
                fake.get_doc.return_value = Record(name="P")
                result = unwrap(api.generate_project_document)("P", category)
                get_document.assert_called_once_with("P", category)
                render.assert_called_once_with(record)
                self.assertEqual(base64.b64decode(result["content"]), b"native-pdf")
                self.assertEqual(result["filename"], f"P-{category.replace(' ', '-')}.pdf")
                self.assertEqual(result["content_type"], "application/pdf")
                self.assertEqual(result["document"], {"doctype": doctype, "name": "D"})

    def test_standalone_agreement_override_is_not_regenerated(self):
        record = Record(doctype="Customer KSEB Agreement", name="D")
        source = {"category": "KSEB Agreement", "url": "/files/signed.pdf", "origin": "Project upload"}
        with patch.object(api, "frappe") as fake, \
                patch.object(api, "get_document", return_value=record), \
                patch.object(api, "resolve_context", return_value={"sources": [source], "warnings": []}), \
                patch.object(api, "render_document") as render, \
                patch.object(api, "read_file", return_value=(b"signed", {})), \
                patch.object(api, "select_pdf_pages", return_value=b"signed"):
            fake.get_doc.return_value = Record(name="P")
            result = unwrap(api.generate_project_document)("P", "KSEB Agreement")
        render.assert_not_called()
        self.assertEqual(base64.b64decode(result["content"]), b"signed")

    def test_standalone_generation_checks_permissions_and_rejects_unknown_action(self):
        with patch.object(api, "frappe") as fake, patch.object(api, "resolve_context") as resolve:
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                unwrap(api.generate_project_document)("P", "Sales Invoice")
            fake.get_doc.assert_not_called()
            fake.get_doc.return_value = Record(name="P", denied=True)
            with self.assertRaises(frappe.PermissionError):
                unwrap(api.generate_project_document)("P", "SLD")
            resolve.assert_not_called()

    def test_report_rendering_does_not_read_agreements(self):
        context = {"warnings": [], "sources": [{"category": category, "url": "/files/agreement.pdf"}
                                               for category in AGREEMENT_SECTIONS]}
        with patch.object(api, "read_file") as read:
            api._render_sources("P", context)
        read.assert_not_called()
