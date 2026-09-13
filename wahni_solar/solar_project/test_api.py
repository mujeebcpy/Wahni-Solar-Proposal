import hashlib
import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import frappe

from wahni_solar.solar_project import api
from wahni_solar.solar_project import sources as source_module
from wahni_solar.solar_project.constants import LEGACY_PANEL_CATEGORIES, LIBRARY_CATEGORIES, PANEL_DOCUMENT
from wahni_solar.solar_project.documents import read_pdf
from wahni_solar.solar_project.sources import public_context, resolve_customer_address, select_annexure, select_bank, select_library


class Record(frappe._dict):
    def check_permission(self, permission):
        if self.get("denied"):
            raise frappe.PermissionError

    def db_set(self, key, value=None, **kwargs):
        self.update(key if isinstance(key, dict) else {key: value})


class TestReportSources(unittest.TestCase):
    def test_customer_primary_address_takes_precedence(self):
        customer = Record(name="C", customer_primary_address="A")
        linked = MagicMock(return_value=Record(name="A", city="Puthukkad", county="Thrissur"))
        with patch.object(source_module.frappe, "get_list") as query:
            address = resolve_customer_address(customer, linked, [])
        self.assertEqual(address.name, "A")
        linked.assert_called_once_with("Address", "A")
        query.assert_not_called()

    def test_customer_address_selection_is_scoped_and_unambiguous(self):
        customer = Record(name="C")
        linked = MagicMock(side_effect=lambda doctype, name: Record(name=name))
        for addresses, expected in [
            ([Record(name="A", is_primary_address=0)], "A"),
            ([Record(name="A", is_primary_address=0), Record(name="B", is_primary_address=1)], "B"),
            ([Record(name="A", is_primary_address=0), Record(name="B", is_primary_address=0)], None),
            ([], None),
        ]:
            with patch.object(source_module.frappe, "get_list", return_value=addresses) as query:
                result = resolve_customer_address(customer, linked, [])
            self.assertEqual(result.name if result else None, expected)
            self.assertIn(["Dynamic Link", "link_name", "=", "C"], query.call_args.kwargs["filters"])
        warnings = []
        with patch.object(source_module.frappe, "get_list", side_effect=frappe.PermissionError):
            self.assertIsNone(resolve_customer_address(customer, linked, warnings))
        self.assertIn("unavailable", warnings[0])

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

    def test_reported_grid_00004_annexure_filenames(self):
        names = [
            "Annexure-1-KSEB-GRID-00004ef1316.pdf",
            "Annexure-2-KSEB-GRID-00004cc0774.pdf",
            "Annexure-3-KSEB-GRID-0000404e9d1.pdf",
        ]
        files = [Record(file_name=name, file_url=f"/private/files/{name}") for name in names]
        for number, filename in enumerate(names, 1):
            self.assertEqual(select_annexure(files, number).file_name, filename)

    def test_annexures_match_renamed_suffixed_and_roman_filenames(self):
        files = [
            Record(file_name="Annexure_1_KSEB-GRID-00004_a1b2c3.pdf", file_url="/private/files/one.pdf"),
            Record(file_name="KSEB Annexure II.pdf", file_url="/private/files/two.pdf"),
            Record(file_name="Download.pdf", file_url="/private/files/Annexure%20III%20signed.pdf"),
            Record(file_name="Annexure-1-KSEB-GRID-00004.pdf", file_url="/private/files/older.pdf"),
        ]
        for number, name in ((1, "one"), (2, "two"), (3, "Annexure%20III%20signed")):
            self.assertEqual(select_annexure(files, number).file_url, f"/private/files/{name}.pdf")
        self.assertIsNone(select_annexure([Record(file_name="Annexure-10.pdf", file_url="/files/ten.pdf")], 1))
        self.assertIsNone(select_annexure([Record(file_name="Annexure-I.pdf", file_url="/files/Annexure-II.pdf")], 1))
        self.assertIsNone(select_annexure([Record(file_name="Annexure-I.qet", file_url="/files/Annexure-I.qet")], 1))
    def test_bank_defaults_and_ambiguity(self):
        one = frappe._dict(name="one", is_default=0)
        two = frappe._dict(name="two", is_default=1)
        self.assertIs(select_bank([one]), one)
        self.assertIs(select_bank([one, two]), two)
        one.is_default = 1
        self.assertIsNone(select_bank([one, two]))
        self.assertIsNone(select_bank([]))

    def test_library_brand_model_priority_and_ambiguity(self):
        common = frappe._dict(name="common", category="Inverter BIS", brand="", model="")
        enphase = frappe._dict(name="enphase", category="Inverter BIS", brand="Enphase", model="")
        model = frappe._dict(name="model", category="Inverter BIS", brand="Enphase", model="IQ8P")
        entries = [common, enphase, model]
        self.assertEqual(select_library(entries, "Inverter BIS", "Vsole", set())[0].name, "common")
        self.assertEqual(select_library(entries, "Inverter BIS", "Enphase", set())[0].name, "enphase")
        self.assertEqual(select_library(entries, "Inverter BIS", "Enphase", {"IQ8P"})[0].name, "model")
        entries.append(frappe._dict(enphase))
        selected, reason = select_library(entries, "Inverter BIS", "Enphase", set())
        self.assertIsNone(selected)
        self.assertIn("Several", reason)

    def test_combined_panel_selection_requires_exact_brand_and_watt_peak(self):
        entries = [Record(name=f"{brand}-{wp}", category=PANEL_DOCUMENT,
                          brand=brand, panel_watt_peak=wp, model="")
                   for brand, wp in [("Adani", 600), ("Adani", 630), ("Premier", 600), ("", 600), ("Adani", 0)]]
        for brand, wp, expected in [(" Adani ", 600, "Adani-600"), ("ADANI", 630, "Adani-630"),
                                    ("Premier", 600, "Premier-600")]:
            with self.subTest(brand=brand, wp=wp):
                selected, reason = select_library(entries, PANEL_DOCUMENT, brand, set(), wp)
                self.assertEqual(selected.name, expected)
                self.assertIsNone(reason)
        for brand, wp in [("", 600), ("Adani", None), ("Adani", 0), ("Adani", -600),
                          ("Adani", 650), ("Premier/Adani", 600), ("Unknown", 600)]:
            with self.subTest(brand=brand, wp=wp):
                selected, reason = select_library(entries, PANEL_DOCUMENT, brand, set(), wp)
                self.assertIsNone(selected)
                self.assertTrue(reason)
        entries.append(Record(entries[0], model="PANEL-600"))
        selected, reason = select_library(entries, PANEL_DOCUMENT, "Adani", {"PANEL-600"}, 600)
        self.assertIsNone(selected)
        self.assertIn("Several", reason)

    def test_combined_panel_library_validation(self):
        from wahni_solar.solar_project.doctype.project_report_document.project_report_document import ProjectReportDocument

        for brand, wp in [("", 600), ("Adani", 0), ("Adani", -600)]:
            doc = Record(category=PANEL_DOCUMENT, brand=brand, panel_watt_peak=wp, enabled=1)
            with patch.object(frappe, "throw", side_effect=ValueError), self.assertRaises(ValueError):
                ProjectReportDocument.validate(doc)
        doc = Record(category=PANEL_DOCUMENT, brand=" Adani ", panel_watt_peak=630, enabled=1, model="OLD")
        ProjectReportDocument.validate(doc)
        self.assertEqual(doc.brand, "Adani")
        self.assertEqual(doc.model, "")

    def test_separate_panel_categories_are_only_allowed_on_existing_records(self):
        from wahni_solar.solar_project.doctype.project_report_document.project_report_document import ProjectReportDocument

        for category in LEGACY_PANEL_CATEGORIES:
            for previous in (None, Record(category="Cover Page"), Record(category=category)):
                doc = Record(category=category, brand="Adani", enabled=0)
                doc.get_doc_before_save = lambda: previous
                with patch.object(frappe, "throw", side_effect=ValueError):
                    if previous and previous.category == category:
                        ProjectReportDocument.validate(doc)
                    else:
                        with self.assertRaises(ValueError):
                            ProjectReportDocument.validate(doc)

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

    def test_public_context_excludes_bank_and_private_snapshot_values(self):
        result = public_context({"grid_choices": [], "warnings": [], "bank": {"bank_account_no": "secret"},
                                 "sources": [{"category": "Cover Page", "url": "/private/files/x.pdf"}]})
        self.assertNotIn("secret", str(result))
        self.assertNotIn("/private/files", str(result))
        self.assertTrue(result["documents"][0]["optional"])

    def test_project_upload_categories_cannot_repeat(self):
        doc = MagicMock()
        doc.get.return_value = [frappe._dict(category="Cover Page", file=None), frappe._dict(category="Cover Page", file=None)]
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

    def test_resolve_links_project_overrides_and_existing_invoice(self):
        records = {
            ("Project", "P"): Record(name="P", customer="C", custom_solar_proposal="S",
                                     custom_panel_watt_peak=630,
                                     custom_report_attachments=[Record(category="Cover Page", file="/files/project.pdf")]),
            ("Customer", "C"): Record(name="C", lead_name="L", customer_primary_address="A"),
            ("Address", "A"): Record(name="A", city="Puthukkad", county="Thrissur"),
            ("Lead", "L"): Record(name="L", email_id="test@example.com"),
            ("Solar Proposal", "S"): Record(name="S", lead="L", package_name="PK", capacity_kw=5, panel_brand="Adani"),
            ("Solar Package", "PK"): Record(name="PK", brand="Enphase", connection_type="Three Phase"),
            ("KSEB Grid Check", "G"): Record(name="G", lead="L", consumer_no="123"),
            ("Sales Invoice", "INV"): Record(name="INV", project="P", customer="C", docstatus=1, is_return=0),
        }
        library = [Record(name="Default Cover", category="Cover Page", file="/files/common.pdf"),
                   Record(name="Adani 600", category=PANEL_DOCUMENT, brand="Adani", panel_watt_peak=600, file="/files/600.pdf"),
                   Record(name="Adani 630", category=PANEL_DOCUMENT, brand="Adani", panel_watt_peak=630, file="/files/630.pdf")]
        def lists(doctype, **kwargs):
            return {"KSEB Grid Check": ["G"], "Bank Account": [], "Sales Invoice": ["INV"],
                    "Project Report Document": library}[doctype]
        with patch.object(source_module.frappe, "get_doc", side_effect=lambda dt, name: records[(dt, name)]), \
                patch.object(source_module.frappe, "get_list", side_effect=lists), \
                patch.object(source_module.frappe, "get_all", return_value=[
                    Record(file_name="Annexure-1-G_ab1234.pdf", file_url="/private/files/anx1.pdf"),
                    Record(file_name="Annexure II.pdf", file_url="/private/files/anx2.pdf"),
                    Record(file_name="Annexure_3.pdf", file_url="/private/files/anx3.pdf"),
                ]) as attachments:
            context = source_module.resolve_context("P")
            project = records[("Project", "P")]
            project.custom_report_attachments.append(Record(category=PANEL_DOCUMENT, file="/files/panel-override.pdf"))
            project.custom_panel_watt_peak = 0
            overridden = source_module.resolve_context("P")
        selected = {row["category"]: row for row in context["sources"]}
        self.assertEqual(selected["Cover Page"]["url"], "/files/project.pdf")
        self.assertEqual(selected["Cover Page"]["origin"], "Project upload")
        self.assertEqual(selected["Sales Invoice"]["invoice"], "INV")
        self.assertEqual(selected["Annexure I"]["url"], "/private/files/anx1.pdf")
        self.assertEqual(selected["Annexure II"]["url"], "/private/files/anx2.pdf")
        self.assertEqual(selected["Annexure III"]["url"], "/private/files/anx3.pdf")
        self.assertEqual(attachments.call_count, 2)
        self.assertEqual(attachments.call_args.kwargs["filters"]["attached_to_name"], "G")
        self.assertEqual(attachments.call_args.kwargs["filters"]["attached_to_doctype"], "KSEB Grid Check")
        self.assertEqual(context["grid"]["consumer_no"], "123")
        self.assertEqual(context["package"]["connection_type"], "Three Phase")
        self.assertNotIn("connection_type", context["proposal"])
        self.assertEqual(context["customer_address"], {"name": "A", "city": "Puthukkad", "county": "Thrissur"})
        self.assertIn({"doctype": "Address", "name": "A"}, context["permissions"])
        self.assertEqual(selected[PANEL_DOCUMENT]["url"], "/files/630.pdf")
        self.assertEqual(selected[PANEL_DOCUMENT]["panel_watt_peak"], 630)
        self.assertEqual(context["panel_watt_peak"], 630)
        self.assertFalse(set(LEGACY_PANEL_CATEGORIES) & selected.keys())
        override = next(row for row in overridden["sources"] if row["category"] == PANEL_DOCUMENT)
        self.assertEqual(override["url"], "/files/panel-override.pdf")
        self.assertEqual(override["origin"], "Project upload")

    def test_worker_merges_combined_panel_once_and_supports_older_snapshots(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=200, height=200)
        buffer = BytesIO()
        writer.write(buffer)
        pdf = buffer.getvalue()
        for categories in [(PANEL_DOCUMENT,), LEGACY_PANEL_CATEGORIES]:
            with self.subTest(categories=categories):
                context = {"sources": [{"category": category, "reason": "No document available."}
                                       for category in LIBRARY_CATEGORIES if category != PANEL_DOCUMENT],
                           "permissions": [], "warnings": []}
                for category in categories:
                    context["sources"].append({"category": category, "url": "/files/panel.pdf",
                                               "origin": "Library", "doctype": "Project Report Document", "name": "Panel",
                                               "brand": "Adani", "panel_watt_peak": 630})
                with patch.object(api, "read_file", return_value=(pdf, {})):
                    snapshot = api._snapshot(context)
                report = Record(name="R", project="P", requested_by="user", status="Queued", input_snapshot="/files/snapshot.zip")
                fake = MagicMock()
                fake.session.user = "user"
                fake.get_doc.side_effect = lambda dt, name: report if dt == "Project Report" else Record(name=name)
                fake.db.get_value.return_value = 1
                with patch.object(api, "frappe", fake), patch.object(api, "read_file", return_value=(snapshot, {})), \
                        patch.object(api, "_save_output") as save:
                    api.build_report("R")
                self.assertEqual(report.status, "Completed with omissions")
                result = json.loads(report.result)
                self.assertEqual([row["category"] for row in result["included"]], list(categories))
                self.assertEqual(len(read_pdf(save.call_args.args[2]).pages), 2 * len(categories))
                self.assertEqual(result["sources"][0]["panel_watt_peak"], 630)

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

    def test_worker_includes_available_forms_and_preserves_uploaded_override(self):
        folder = Path(__file__).parent / "templates"
        original = (folder / "Completion_Certificate_Fillable.pdf").read_bytes()
        context = {"sources": [{"category": category, "reason": "No document available."}
                               for category in LIBRARY_CATEGORIES],
                   "permissions": [], "warnings": [], "grid": {"consumer_name": "NEW CUSTOMER"}}
        completion = next(row for row in context["sources"] if row["category"] == "Project Completion Report")
        completion.update(url="/files/edited.pdf", origin="Project upload", doctype="Project", name="P")
        with patch.object(api, "read_file", return_value=(original, {})):
            snapshot = api._snapshot(context)
        report = Record(name="R", project="P", requested_by="user", status="Queued", input_snapshot="/private/files/snapshot.zip")
        fake = MagicMock()
        fake.session.user = "user"
        fake.get_doc.side_effect = lambda dt, name: report if dt == "Project Report" else Record(name=name)
        fake.db.get_value.return_value = 1
        saved = {}
        def save(filename, content, *args, **kwargs):
            saved[filename] = content
            self.assertEqual(kwargs["is_private"], 1)
            return Record(file_url=f"/private/files/{filename}")
        with patch.object(api, "frappe", fake), patch.object(api, "read_file", return_value=(snapshot, {})), \
                patch.object(api, "save_file", side_effect=save):
            api.build_report("R")
        self.assertEqual(report.status, "Completed with omissions")
        result = json.loads(report.result)
        self.assertEqual([row["category"] for row in result["included"]], ["Project Completion Report"])
        self.assertFalse({"Cover Page", "End Page", "Sales Invoice"} & {row["category"] for row in result["omitted"]})
        fields = read_pdf(saved["R-Project-Report.pdf"]).get_fields()
        # A Project override is already completed by the user and must never be autofilled again.
        self.assertEqual(fields["section_00.customer_name"]["/V"], "Sunil P M")

    def test_interrupted_job_is_marked_failed(self):
        from datetime import datetime, timedelta
        report = Record(name="R", project="P", status="Running", modified=datetime.now() - timedelta(minutes=5))
        with patch.object(api, "get_job_status", return_value="failed"), patch.object(api, "_project_status"), \
                patch.object(api, "now_datetime", return_value=datetime.now()):
            api._recover_interrupted(report)
        self.assertEqual(report.status, "Failed")

    def test_generated_forms_are_only_in_combined_pdf_and_qet_is_separate(self):
        folder = Path(__file__).parent / "templates"
        templates = {
            "Check List": "Check_List_Fillable.pdf",
            "Project Completion Report": "Completion_Certificate_Fillable.pdf",
            "SLD Template": "SLD_Enphase.qet",
        }
        context = {"sources": [{"category": category, "reason": "No document available."}
                               for category in LIBRARY_CATEGORIES], "permissions": [], "warnings": [],
                   "grid": {"consumer_name": "NEW CUSTOMER"}, "proposal": {"capacity_kw": 5}}
        contents = {}
        for source in context["sources"]:
            category = source["category"]
            if category in templates:
                url = "/files/" + templates[category]
                contents[url] = (folder / templates[category]).read_bytes()
                source.update(url=url, origin="Library", doctype="Project Report Document", name=category)
        with patch.object(api, "read_file", side_effect=lambda url: (contents[url], {})):
            snapshot = api._snapshot(context)
        report = Record(name="R", project="P", requested_by="user", status="Queued", input_snapshot="/private/files/snapshot.zip")
        fake = MagicMock()
        fake.session.user = "user"
        fake.get_doc.side_effect = lambda dt, name: report if dt == "Project Report" else Record(name=name)
        fake.db.get_value.return_value = 1
        saved = {}
        def save(filename, content, *args, **kwargs):
            saved[filename] = content
            return Record(file_url=f"/private/files/{filename}")
        with patch.object(api, "frappe", fake), patch.object(api, "read_file", return_value=(snapshot, {})), \
                patch.object(api, "save_file", side_effect=save):
            api.build_report("R")
        self.assertEqual(set(saved), {"R-SLD.qet", "R-Project-Report.pdf"})
        self.assertEqual(report.sld_qet, "/private/files/R-SLD.qet")
        self.assertNotIn("checklist_pdf", api._result(report))
        self.assertNotIn("completion_pdf", api._result(report))
        reader = read_pdf(saved["R-Project-Report.pdf"])
        self.assertEqual(len(reader.pages), 3)
        fields = reader.get_fields()
        self.assertEqual(fields["section_00.solar_plant_owner"]["/V"], "NEW CUSTOMER")
        self.assertEqual(fields["section_01.customer_name"]["/V"], "NEW CUSTOMER")
        original = read_pdf(contents["/files/Check_List_Fillable.pdf"]).get_fields()
        self.assertEqual(fields["section_00.installation_resistance"]["/V"], original["installation_resistance"]["/V"])

    def test_seed_library_does_not_replace_existing_user_files(self):
        from wahni_solar.solar_project import setup
        fake = MagicMock()
        fake.get_app_path.return_value = str(Path(__file__).parent / "templates")
        fake.db.exists.return_value = True
        with patch.object(setup, "frappe", fake), patch.object(setup, "save_file") as save:
            setup.seed_library()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
