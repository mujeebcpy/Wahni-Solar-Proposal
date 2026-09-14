"""Editable PDF forms, report assembly and SLD personalization."""

import unittest
import xml.etree.ElementTree as ET

from pypdf import PdfWriter

from wahni_solar.solar_project.constants import SECTIONS
from wahni_solar.solar_project.documents import (
    fill_form, form_values, merge_pdfs, pdf_bytes, personalise_qet, phase, read_pdf, select_pdf_pages,
)
from wahni_solar.solar_project.tests.helpers import TEMPLATES


class TestReportDocuments(unittest.TestCase):
    def setUp(self):
        self.context = {
            "grid": {"consumer_name": "Test & Customer", "consumer_no": "1234567890123",
                     "registered_mobile": "9000000000", "customer_address": "A < B, Thrissur",
                     "phase": "LT-1/Three", "proposed_solar_capacity": 4},
            "lead": {"email_id": "test@example.com", "mobile_no": "9000000001"},
            "proposal": {"capacity_kw": 5.5, "panel_brand": "Adani", "panel_count": 10},
            "package": {"brand": "Enphase", "grid_type": "On-Grid", "system_type": "Micro", "connection_type": "Single Phase"},
            "bank": {"account_name": "Test Customer", "bank": "Test Bank", "branch_code": "TEST0001234", "bank_account_no": "00012345"},
        }

    def form(self, filename, category):
        return fill_form((TEMPLATES / filename).read_bytes(), form_values(self.context)[category])[0]

    def test_agreements_fill_actual_fields_and_keep_signing_details_editable(self):
        self.context.update(
            generation_date="2026-09-14",
            customer={"customer_name": "Standard Customer"},
            customer_address={"address_line1": "House 12", "address_line2": "Main Road",
                              "city": "Thrissur", "state": "Kerala", "country": "India", "pincode": "680001"},
            panel={"brand": "Panel Make", "custom_model": "P550", "custom_panel_watt_peak": 600},
            inverter={"brand": "Inverter Make", "custom_model": "IQ8P", "custom_rated_capacity": 480},
        )
        self.context["grid"]["section"] = "Test Section"
        self.context["proposal"]["project_cost"] = 300000
        for category, filename, pages in (
            ("KSEB Agreement", "KSEB_Agreement_Fillable.pdf", 4),
            ("Customer Vendor Agreement", "Solar_Customer_Vendor_Agreement_Fillable.pdf", 5),
        ):
            with self.subTest(category=category):
                reader = read_pdf(self.form(filename, category))
                fields = reader.get_fields()
                self.assertEqual(len(reader.pages), pages)
                self.assertEqual(fields["name"]["/V"], "Standard Customer")
                self.assertEqual(fields["consumer_no"]["/V"], "1234567890123")
                self.assertEqual(fields["system_capacity"]["/V"], "5.5kW")
                self.assertEqual(fields["customer_address"]["/V"], "House 12, Main Road, Thrissur, Kerala, India, 680001")
                self.assertFalse(fields["name"].get("/Ff", 0) & 1)
                if category == "KSEB Agreement":
                    self.assertEqual(fields["customer_pincode"]["/V"], "680001")
                    self.assertEqual(fields["electrical_section"]["/V"], "Test Section")
                    self.assertEqual(fields["agreement_date"]["/V"], "14")
                    self.assertEqual(fields["date_month_year"]["/V"], "September 2026")
                    self.assertFalse(fields["agreement_place"].get("/V"))
                else:
                    self.assertEqual(fields["applicant_name"]["/V"], "Standard Customer")
                    self.assertEqual(fields["applicant_address"]["/V"], fields["customer_address"]["/V"])
                    for key, value in {"solar_panel_make": "Panel Make", "solar_panel_model": "P550",
                                       "solar_panel_capacity": "600 Wp", "inverter_make": "Inverter Make",
                                       "inverter_model": "IQ8P", "inverter_capacity": "480", "system_price": "300000"}.items():
                        self.assertEqual(fields[key]["/V"], value)
                    self.assertEqual(fields["date"]["/V"], "14-09-2026")

    def test_agreement_address_falls_back_to_grid_and_missing_data_stays_blank(self):
        self.context["customer_address"] = {"city": "Thrissur"}
        self.context["grid"]["customer_address"] = "KSEB House, Thrissur 680002"
        values = form_values(self.context)
        self.assertEqual(values["KSEB Agreement"]["customer_address"], "KSEB House, Thrissur 680002")
        self.assertEqual(values["KSEB Agreement"]["customer_pincode"], "680002")
        self.assertEqual(values["Customer Vendor Agreement"]["applicant_name"], "Test & Customer")
        for watt_peak in (None, 0):
            self.context["panel"] = {"custom_panel_watt_peak": watt_peak}
            vendor = form_values(self.context)["Customer Vendor Agreement"]
            self.assertEqual(vendor["solar_panel_capacity"], "")
            self.assertEqual(vendor["inverter_model"], "")

    def test_forms_only_replace_available_values_and_keep_template_defaults(self):
        checklist = self.form("Check_List_Fillable.pdf", "Check List")
        fields = read_pdf(checklist).get_fields()
        self.assertEqual(fields["solar_plant_owner"]["/V"], "Test & Customer")
        self.assertEqual(fields["bank_account_number"]["/V"], "00012345")
        self.assertEqual(fields["bank_ifsc_code"]["/V"], "TEST0001234")
        original = read_pdf((TEMPLATES / "Check_List_Fillable.pdf").read_bytes()).get_fields()
        mapped = form_values(self.context)["Check List"]
        for key, field in original.items():
            if not mapped.get(key):
                self.assertEqual(fields[key].get("/V"), field.get("/V"), key)
                self.assertEqual(fields[key].get("/DV"), field.get("/DV"), key)
        self.assertEqual(fields["inverter_make_and_serial_number"]["/V"], "Enphase")
        self.assertEqual(fields["plant_total_capacity"]["/V"], "4kW")
        self.assertEqual(fields["solar_plant_owner"]["/DV"], "Test & Customer")
        values = " ".join(str(field.get("/V", "")) for field in fields.values())
        self.assertNotIn("251227", values)
        self.assertNotIn("Renewsys", values)
        completion = self.form("Completion_Certificate_Fillable.pdf", "Project Completion Report")
        fields = read_pdf(completion).get_fields()
        self.assertEqual(fields["customer_name"]["/V"], "Test & Customer")
        original = read_pdf((TEMPLATES / "Completion_Certificate_Fillable.pdf").read_bytes()).get_fields()
        self.assertEqual(fields["whole_installation_insulation_resistance"]["/V"],
                         original["whole_installation_insulation_resistance"]["/V"])
        self.assertNotIn("Sunil", str(fields))

    def test_empty_values_do_not_erase_template_values_or_defaults(self):
        for filename in ("Check_List_Fillable.pdf", "Completion_Certificate_Fillable.pdf"):
            content = (TEMPLATES / filename).read_bytes()
            original = read_pdf(content).get_fields()
            values = {key: (None if index % 2 else "   ") for index, key in enumerate(original)}
            filled, missing = fill_form(content, values)
            fields = read_pdf(filled).get_fields()
            for key, field in original.items():
                self.assertEqual(fields[key].get("/V"), field.get("/V"), key)
                self.assertEqual(fields[key].get("/DV"), field.get("/DV"), key)
                if field.get("/V"):
                    self.assertNotIn(key, missing)

    def test_order_bookmarks_and_cover_end_pages(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        cover = pdf_bytes(writer)
        checklist = self.form("Check_List_Fillable.pdf", "Check List")
        merged, manifest = merge_pdfs([("Cover Page", cover), ("Check List", checklist), ("End Page", cover)])
        self.assertEqual([(row["page_from"], row["page_to"]) for row in manifest], [(1, 1), (2, 3), (4, 4)])
        reader = read_pdf(merged)
        self.assertEqual([item.title for item in reader.outline], ["Cover Page", "Check List", "End Page"])
        self.assertEqual(SECTIONS[0], "Cover Page")
        self.assertEqual(SECTIONS[-1], "End Page")
        self.assertLess(SECTIONS.index("ACDB SPD Datasheet"), SECTIONS.index("ACDB MCB Datasheet"))

    def test_inverter_ranges_have_no_duplicate_pages(self):
        for filename, ranges in [
            ("16.IQ8P Microinverter n BIS.pdf", [(1, 4), (5, 6)]),
            ("Vsole_Micro Inverter_Datasheet n BIS.pdf", [(1, 1), (2, 2)]),
        ]:
            original = read_pdf((TEMPLATES / filename).read_bytes())
            selected = [select_pdf_pages((TEMPLATES / filename).read_bytes(), start, end) for start, end in ranges]
            merged, _ = merge_pdfs(list(zip(["Datasheet", "BIS"], selected)))
            actual = read_pdf(merged)
            self.assertEqual(len(actual.pages), len(original.pages))
            self.assertEqual([page.extract_text() for page in actual.pages], [page.extract_text() for page in original.pages])

    def test_invalid_pdf_and_ranges_are_rejected(self):
        with self.assertRaises(Exception):
            select_pdf_pages(b"not a PDF")
        with self.assertRaises(ValueError):
            select_pdf_pages((TEMPLATES / "Check_List_Fillable.pdf").read_bytes(), 1, 9)
        with self.assertRaises(ValueError):
            merge_pdfs([])
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.encrypt("password")
        with self.assertRaises(ValueError):
            read_pdf(pdf_bytes(writer))

    def test_both_qet_templates_keep_circuits_and_replace_properties(self):
        for filename in ("SLD_Enphase.qet", "SLD_vsole.qet"):
            template = (TEMPLATES / filename).read_bytes()
            result, missing = personalise_qet(template, self.context)
            self.assertEqual(missing, [])
            original, actual = ET.fromstring(template), ET.fromstring(result)
            for old, new in zip(original.findall("diagram"), actual.findall("diagram")):
                props = {node.get("name"): node.text for node in new.findall("./properties/property")}
                self.assertEqual(props["cstmr"], "Test & Customer")
                self.assertEqual(props["cnsnumb"], "1234567890123")
                self.assertEqual(props["cntrdmd"], "5.5kW")
                self.assertEqual(props["plntcpt"], "5.5kW")
                self.assertEqual(props["cntype"], "3 Phase")
                self.assertEqual(props["plntype"], "1 Phase")
                self.assertEqual(new.get("locmach"), "A < B, Thrissur")
                for tag in ("elements", "conductors", "inputs"):
                    self.assertEqual(ET.tostring(old.find(tag)), ET.tostring(new.find(tag)))

    def test_qet_connection_type_uses_package(self):
        for value, expected in [("Three Phase", "3 Phase"), (None, None)]:
            self.context["package"]["connection_type"] = value
            result, missing = personalise_qet((TEMPLATES / "SLD_Enphase.qet").read_bytes(), self.context)
            actual = ET.fromstring(result)
            self.assertEqual(actual.find("./diagram/properties/property[@name='plntype']").text, expected)
            self.assertEqual("plntype" in missing, value is None)

    def test_unknown_qet_fields_do_not_keep_sample_values(self):
        result, missing = personalise_qet((TEMPLATES / "SLD_vsole.qet").read_bytes(), {})
        self.assertIn("cstmr", missing)
        self.assertIn("location", missing)
        actual = ET.fromstring(result)
        self.assertIsNone(actual.find("./diagram/properties/property[@name='cstmr']").text)
        self.assertEqual(phase("LT-1/Three"), "3 Phase")
        self.assertEqual(phase("unknown"), "")
        with self.assertRaises(ValueError):
            personalise_qet(b'<!DOCTYPE project [<!ENTITY x "test">]><project><diagram/></project>', {})

    def test_qet_location_uses_customer_city_and_county(self):
        template = (TEMPLATES / "SLD_Enphase.qet").read_bytes()
        for address, expected in [
            ({"city": " Puthukkad ", "county": " Thrissur ", "country": "India"}, "Puthukkad, Thrissur"),
            ({"city": "Puthukkad", "county": ""}, "Puthukkad"),
            ({"city": "", "county": "Thrissur"}, "Thrissur"),
            ({}, self.context["grid"]["customer_address"]),
        ]:
            self.context["customer_address"] = address
            result, missing = personalise_qet(template, self.context)
            self.assertEqual(ET.fromstring(result).find("diagram").get("locmach"), expected)
            self.assertNotIn("location", missing)

    def test_missing_bank_and_uncertain_panel_make_are_blank(self):
        self.context["bank"] = {}
        self.context["proposal"]["panel_brand"] = "Premier/Adani"
        values = form_values(self.context)["Check List"]
        self.assertEqual(values["bank_account_number"], "")
        self.assertNotIn("pv_installations_make_and_total_number", values)
