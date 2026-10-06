"""Optional wkhtmltopdf smoke tests for the shipped HTML and embedded fonts."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jinja2 import Environment
from pypdf import PdfReader

from wahni_solar.solar_project.documents import form_values
from wahni_solar.solar_project.tests.helpers import Record

BASE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("wkhtmltopdf"), "wkhtmltopdf is required for PDF smoke tests")
class TestNativePDFs(unittest.TestCase):
    def render(self, path, doc):
        fmt = json.loads(path.read_text())
        markup = Environment().from_string(fmt["html"]).render(doc=doc)
        source = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' + fmt["css"] + '</style></head><body style="margin:0"><div class="print-format">' + markup + '</div></body></html>'
        # Like Frappe 15: page margins come from the top-level `.print-format` rule
        # (the Print Format margin fields are not used by wkhtmltopdf), print media.
        top_level = re.match(r"(?:[^@]|@(?!media))*", re.sub(r"/\*.*?\*/", "", fmt["css"], flags=re.S)).group(0)
        css_margins = dict(re.findall(r"margin-(top|bottom|left|right)\s*:\s*([\d.]+mm)", top_level))
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / "print.html"
            pdf = Path(directory) / "print.pdf"
            html.write_text(source)
            command = ["wkhtmltopdf", "--quiet", "--print-media-type", "--disable-smart-shrinking", "--encoding", "utf-8",
                       "--page-size", "A4", "--load-error-handling", "ignore", "--load-media-error-handling", "ignore"]
            for side in ("top", "bottom", "left", "right"):
                command.extend([f"--margin-{side}", css_margins.get(side) or str(fmt.get(f"margin_{side}", 14))])
            # screen-only preview artwork (/files/...) can't load from a temp file; the PDF is still written
            subprocess.run([*command, str(html), str(pdf)], capture_output=True, timeout=60)
            reader = PdfReader(pdf)
            self.assertFalse(reader.get_fields(), fmt["name"])
            self.assertNotIn("None", " ".join(page.extract_text() for page in reader.pages))
            return reader

    def project_document(self, doctype, address="Test House, Thrissur 680001"):
        from wahni_solar.solar_project.project_documents import category_for
        slug = doctype.lower().replace(" ", "_")
        schema = json.loads((BASE / "doctype" / slug / f"{slug}.json").read_text())
        values = form_values({"customer": {"customer_name": "Test Customer"},
                              "grid": {"consumer_name": "Test Customer", "customer_address": address,
                                       "consumer_no": "1234567890123", "phase": "Three Phase", "proposed_solar_capacity": 5},
                              "proposal": {"capacity_kw": 5, "panel_brand": "Adani", "panel_count": 10, "project_cost": 300000},
                              "package": {"brand": "Enphase", "grid_type": "On Grid"}})[category_for(doctype)]
        for field in schema["fields"]:
            if field["fieldtype"] in ("Section Break", "HTML", "Link"):
                continue
            values[field["fieldname"]] = field.get("default", "")
            if values[field["fieldname"]] == "Today":
                values[field["fieldname"]] = "01-10-2026"
        values.update(date="01-10-2026", agreement_date="1", date_month_year="October 2026")
        return Record(print_context={"values": values}), BASE / "print_format" / slug / f"{slug}.json"

    def test_all_seven_formats_render_without_form_fields_and_embed_manjari(self):
        from wahni_kseb.annexure import printing
        for doctype, pages in (("Customer Vendor Agreement", 5), ("Customer KSEB Agreement", 4),
                                ("Solar Installation Checklist", 2), ("Solar Completion Certificate", 1)):
            with self.subTest(doctype=doctype):
                doc, path = self.project_document(doctype)
                self.assertEqual(len(self.render(path, doc).pages), pages)
        root = Path(printing.__file__).resolve().parents[1]
        grid = Record(consumer_name="അനിൽ കുമാർ", consumer_no="1234567890123", proposed_solar_capacity=5,
                      customer_address="തൃശ്ശൂർ, കേരളം", connected_load="5 kW", is_rooftop="Rooftop")
        grid.annexure_context = printing.print_context(grid)
        for path in (root / "kseb_grid_data/print_format").glob("*/*.json"):
            with self.subTest(format=path.stem):
                pdf = self.render(path, grid)
                self.assertEqual(len(pdf.pages), 1)
                fonts = pdf.pages[0]["/Resources"]["/Font"].get_object()
                names = [str(font.get_object().get("/BaseFont")) for font in fonts.values()]
                self.assertTrue(any("Manjari-Regular" in name for name in names), names)
                self.assertTrue(any("Manjari-Bold" in name for name in names), names)

    def test_long_addresses_wrap_without_losing_end_of_value(self):
        address = "Long customer address with multiple locations and building details. " * 8 + "ENDOFADDRESS"
        for doctype in ("Customer Vendor Agreement", "Customer KSEB Agreement", "Solar Completion Certificate", "Solar Installation Checklist"):
            with self.subTest(doctype=doctype):
                doc, path = self.project_document(doctype, address)
                pdf = self.render(path, doc)
                text = " ".join(page.extract_text() for page in pdf.pages)
                self.assertIn("ENDOFADDRESS", text)
