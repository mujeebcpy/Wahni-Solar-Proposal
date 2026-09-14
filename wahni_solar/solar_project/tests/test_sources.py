"""Customer, equipment and document source selection."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.solar_project import sources as source_module
from wahni_solar.solar_project.constants import LEGACY_PANEL_CATEGORIES, PANEL_DOCUMENT
from wahni_solar.solar_project.sources import public_context, resolve_customer_address, select_annexure, select_bank, select_library
from wahni_solar.solar_project.tests.helpers import Record


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

    def test_annexures_match_filenames_with_hash_suffixes(self):
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

    def test_public_context_excludes_bank_and_private_snapshot_values(self):
        result = public_context({"grid_choices": [], "warnings": [], "bank": {"bank_account_no": "secret"},
                                 "sources": [{"category": "Cover Page", "url": "/private/files/x.pdf"}]})
        self.assertNotIn("secret", str(result))
        self.assertNotIn("/private/files", str(result))
        self.assertTrue(result["documents"][0]["optional"])

    def test_resolve_links_project_overrides_and_existing_invoice(self):
        records = {
            ("Project", "P"): Record(name="P", customer="C", custom_solar_proposal="S",
                                     custom_panel_item="PANEL-630",
                                     custom_report_attachments=[Record(category="Cover Page", file="/files/project.pdf")]),
            ("Item", "PANEL-630"): Record(name="PANEL-630", item_group="Panel", custom_panel_watt_peak=630),
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
            project.custom_panel_item = None
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
        self.assertEqual(context["customer_address"]["city"], "Puthukkad")
        self.assertEqual(context["customer_address"]["county"], "Thrissur")
        self.assertIn("address_line1", context["customer_address"])
        self.assertIn({"doctype": "Address", "name": "A"}, context["permissions"])
        self.assertEqual(selected[PANEL_DOCUMENT]["url"], "/files/630.pdf")
        self.assertEqual(selected[PANEL_DOCUMENT]["panel_watt_peak"], 630)
        self.assertEqual(context["panel_watt_peak"], 630)
        self.assertEqual(context["panel_item"], "PANEL-630")
        self.assertIn({"doctype": "Item", "name": "PANEL-630"}, context["permissions"])
        self.assertFalse(set(LEGACY_PANEL_CATEGORIES) & selected.keys())
        override = next(row for row in overridden["sources"] if row["category"] == PANEL_DOCUMENT)
        self.assertEqual(override["url"], "/files/panel-override.pdf")
        self.assertEqual(override["origin"], "Project upload")

    def test_panel_item_resolution_checks_permissions_group_and_missing_wattage(self):
        project = Record(name="P", custom_panel_item="PANEL")
        panel = Record(name="PANEL", item_group="Panel", custom_panel_watt_peak=0)
        records = {("Project", "P"): project, ("Item", "PANEL"): panel}
        with patch.object(source_module.frappe, "get_doc", side_effect=lambda dt, name: records[(dt, name)]), \
                patch.object(source_module.frappe, "get_list", return_value=[]), \
                patch.object(source_module.frappe, "throw", side_effect=ValueError):
            for value in (None, 0):
                panel.custom_panel_watt_peak = value
                context = source_module.resolve_context("P")
                source = next(row for row in context["sources"] if row["category"] == PANEL_DOCUMENT)
                self.assertNotIn("url", source)
                self.assertIn("Panel Item", source["reason"])
                self.assertEqual(context["panel_watt_peak"], value)
            panel.denied = True
            with self.assertRaises(frappe.PermissionError):
                source_module.resolve_context("P")
            panel.denied = False
            panel.item_group = "Microinverters"
            with self.assertRaises(ValueError):
                source_module.resolve_context("P")

    def test_agreement_resolution_uses_bom_items_without_invoice_bank_or_annexure_work(self):
        records = {
            ("Project", "P"): Record(name="P", customer="C", custom_solar_proposal="S",
                                     custom_report_sales_invoice="INVALID",
                                     custom_table_project_bom=[Record(item_code="PANEL"), Record(item_code="INV")]),
            ("Customer", "C"): Record(name="C", lead_name="L", customer_primary_address="A", customer_name="Customer"),
            ("Address", "A"): Record(name="A", address_line1="Customer House", pincode="680001"),
            ("Lead", "L"): Record(name="L"),
            ("Solar Proposal", "S"): Record(name="S", lead="L", capacity_kw=5, panel_count=10),
            ("KSEB Grid Check", "G"): Record(name="G", lead="L", consumer_no="123"),
            ("Item", "PANEL"): Record(name="PANEL", item_group="Panel", brand="Adani", custom_model="P500"),
            ("Item", "INV"): Record(name="INV", item_group="Microinverters", brand="Enphase",
                                      custom_model="IQ8P", custom_rated_capacity=480),
        }
        library = [Record(name="Vendor", category="Customer Vendor Agreement", file="/files/vendor.pdf")]
        def lists(doctype, **kwargs):
            return {"KSEB Grid Check": ["G"], "Project Report Document": library}[doctype]
        with patch.object(source_module.frappe, "get_doc", side_effect=lambda dt, name: records[(dt, name)]), \
                patch.object(source_module.frappe, "get_list", side_effect=lists), \
                patch.object(source_module.frappe, "get_all") as attachments:
            context = source_module.resolve_context("P", categories=("Customer Vendor Agreement",))
            self.assertEqual(context["panel"]["custom_model"], "P500")
            self.assertEqual(context["inverter"]["custom_rated_capacity"], 480)
            self.assertEqual(context["customer_address"]["address_line1"], "Customer House")
            self.assertEqual([row["category"] for row in context["sources"]], ["Customer Vendor Agreement"])
            self.assertIn({"doctype": "Item", "name": "INV"}, context["permissions"])
            attachments.assert_not_called()
            records[("Item", "INV")].denied = True
            with self.assertRaises(frappe.PermissionError):
                source_module.resolve_context("P", categories=("Customer Vendor Agreement",))
