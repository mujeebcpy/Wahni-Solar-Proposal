"""Generation requests, annexure reuse and input snapshots."""

import hashlib
import json
import unittest
from inspect import unwrap
from io import BytesIO
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import frappe

from wahni_solar.solar_project import api
from wahni_solar.solar_project.constants import AGREEMENT_SECTIONS
from wahni_solar.solar_project.documents import read_pdf
from wahni_solar.solar_project.tests.helpers import Record, TEMPLATES


class TestReportAPI(unittest.TestCase):
    def test_missing_annexure_reuses_kseb_generator(self):
        grid = MagicMock()
        generate = MagicMock(return_value={"file_url": "/private/files/generated.pdf"})
        fake = MagicMock()
        fake.get_doc.return_value = grid
        fake.get_all.return_value = []
        fake.get_attr.return_value = generate
        with patch.object(api, "frappe", fake):
            for number in (1, 2, 3):
                self.assertEqual(api._ensure_annexure("G", number), "/private/files/generated.pdf")
                fake.get_attr.assert_called_with(f"wahni_kseb.api.generate_annexure{number}")
        generate.assert_called_with(kseb_grid_check="G")
        grid.check_permission.assert_any_call("write")
        self.assertIn("FOR UPDATE", fake.db.sql.call_args.args[0])

    def test_annexure_created_by_another_request_is_reused(self):
        fake = MagicMock()
        fake.get_all.return_value = [Record(file_name="Annexure-1-G_hash.pdf", file_url="/private/files/existing.pdf")]
        with patch.object(api, "frappe", fake):
            self.assertEqual(api._ensure_annexure("G", 1), "/private/files/existing.pdf")
        fake.get_attr.assert_not_called()
        fake.get_doc.return_value.check_permission.assert_called_once_with("read")

    def test_annexure_generation_requires_grid_write_permission(self):
        grid = MagicMock()
        grid.check_permission.side_effect = [None, frappe.PermissionError]
        fake = MagicMock()
        fake.get_doc.return_value = grid
        fake.get_all.return_value = []
        with patch.object(api, "frappe", fake):
            with self.assertRaises(frappe.PermissionError):
                api._ensure_annexure("G", 1)
        fake.get_attr.assert_not_called()

    def test_snapshot_generates_only_missing_annexures_and_records_failures(self):
        context = {"sources": [
            {"category": "Annexure I", "url": "/files/existing.pdf", "origin": "Project upload"},
            {"category": "Annexure II", "name": "G", "annexure_number": 2},
            {"category": "Annexure III", "name": "G", "annexure_number": 3},
        ]}
        with patch.object(api, "_ensure_annexure", side_effect=["/files/new.pdf", ValueError("Solar capacity is missing")]) as generate, \
                patch.object(api, "read_file", side_effect=lambda url: (url.encode(), {})):
            snapshot = api._snapshot(context)
        self.assertEqual([call.args for call in generate.call_args_list], [("G", 2), ("G", 3)])
        with ZipFile(BytesIO(snapshot)) as archive:
            saved = json.loads(archive.read("context.json"))["sources"]
            self.assertEqual(archive.read(saved[0]["archive_path"]), b"/files/existing.pdf")
            self.assertEqual(archive.read(saved[1]["archive_path"]), b"/files/new.pdf")
            self.assertNotIn("archive_path", saved[2])
            self.assertIn("Solar capacity is missing", saved[2]["reason"])

    def test_snapshot_keeps_original_bytes_after_library_replacement(self):
        context = {"sources": [{"category": "Cover Page", "url": "/files/cover.pdf"}]}
        original = b"original bytes"
        with patch.object(api, "read_file", return_value=(original, {"sha256": hashlib.sha256(original).hexdigest()})):
            snapshot = api._snapshot(context)
        with ZipFile(BytesIO(snapshot)) as archive:
            saved = json.loads(archive.read("context.json"))
            self.assertEqual(archive.read(saved["sources"][0]["archive_path"]), original)
            self.assertEqual(saved["sources"][0]["sha256"], hashlib.sha256(original).hexdigest())

    def test_missing_invoice_is_not_rendered(self):
        context = {"sources": [{"category": "Sales Invoice", "reason": "No document available."}]}
        with patch.object(api.frappe, "get_print") as render:
            api._snapshot(context)
            render.assert_not_called()

    def test_unreadable_file_does_not_prevent_other_snapshots(self):
        context = {"sources": [{"category": "Cover Page", "url": "/files/a.pdf"},
                               {"category": "End Page", "url": "/files/b.pdf"}]}
        with patch.object(api, "read_file", side_effect=[ValueError("bad file"), (b"good", {})]):
            snapshot = api._snapshot(context)
        with ZipFile(BytesIO(snapshot)) as archive:
            sources = json.loads(archive.read("context.json"))["sources"]
            self.assertIn("bad file", sources[0]["reason"])
            self.assertNotIn("archive_path", sources[0])
            self.assertEqual(archive.read(sources[1]["archive_path"]), b"good")

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

    def test_repeated_generation_returns_running_report_without_new_snapshot(self):
        report = Record(name="R", project="P", status="Running")
        fake = MagicMock()
        fake.get_doc.side_effect = lambda dt, name: report if dt == "Project Report" else Record(name="P")
        fake.get_all.return_value = ["R"]
        with patch.object(api, "frappe", fake), patch.object(api, "_recover_interrupted"), \
                patch.object(api, "_snapshot") as snapshot, \
                patch.object(frappe.local, "flags", frappe._dict(in_test=True), create=True):
            result = api.generate_project_report("P")
        self.assertEqual(result["name"], "R")
        self.assertIn("FOR UPDATE", fake.db.sql.call_args.args[0])
        snapshot.assert_not_called()

    def test_interrupted_job_is_marked_failed(self):
        from datetime import datetime, timedelta
        report = Record(name="R", project="P", status="Running", modified=datetime.now() - timedelta(minutes=5))
        with patch.object(api, "get_job_status", return_value="failed"), patch.object(api, "_project_status"), \
                patch.object(api, "now_datetime", return_value=datetime.now()):
            api._recover_interrupted(report)
        self.assertEqual(report.status, "Failed")

    def test_standalone_outputs_use_only_requested_source_and_private_project_attachments(self):
        from datetime import datetime

        folder = TEMPLATES
        for category, filename in (("SLD", "SLD_Enphase.qet"),
                                   ("KSEB Agreement", "KSEB_Agreement_Fillable.pdf"),
                                   ("Customer Vendor Agreement", "Solar_Customer_Vendor_Agreement_Fillable.pdf")):
            source_category = "SLD Template" if category == "SLD" else category
            context = {"sources": [{"category": source_category, "url": "/files/template", "origin": "Library"}],
                       "warnings": [], "grid": {"consumer_name": "Test Customer"}, "proposal": {"capacity_kw": 5}}
            with self.subTest(category=category), patch.object(api, "frappe") as fake, \
                    patch.object(api, "resolve_context", return_value=context) as resolve, \
                    patch.object(api, "read_file", return_value=((folder / filename).read_bytes(), {})), \
                    patch.object(api, "save_file", return_value=Record(file_url="/private/files/output")) as save, \
                    patch.object(api, "now_datetime", return_value=datetime(2027, 1, 1, 0, 5)), \
                    patch.object(api, "_ensure_annexure") as annexure:
                fake.get_doc.return_value = Record(name="P")
                result = unwrap(api.generate_project_document)("P", category)
                resolve.assert_called_once_with("P", categories=(source_category,))
                self.assertEqual(result["file_url"], "/private/files/output")
                self.assertEqual(save.call_args.args[2:], ("Project", "P"))
                self.assertEqual(save.call_args.kwargs, {"is_private": 1})
                annexure.assert_not_called()
                fake.enqueue.assert_not_called()
                if category != "SLD":
                    fields = read_pdf(save.call_args.args[1]).get_fields()
                    self.assertEqual(fields["name"]["/V"], "Test Customer")
                    if category == "KSEB Agreement":
                        self.assertEqual(fields["agreement_date"]["/V"], "1")
                        self.assertEqual(fields["date_month_year"]["/V"], "January 2027")
                    else:
                        self.assertEqual(fields["date"]["/V"], "01-01-2027")

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

    def test_report_snapshots_do_not_read_agreements(self):
        context = {"sources": [{"category": category, "url": "/files/agreement.pdf"}
                               for category in AGREEMENT_SECTIONS]}
        with patch.object(api, "read_file") as read:
            api._snapshot(context)
        read.assert_not_called()
