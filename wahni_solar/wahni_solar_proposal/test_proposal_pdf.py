"""Solar Proposal page artwork: stamping and hook scoping."""

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader, PdfWriter

from wahni_solar.wahni_solar_proposal import proposal_pdf


def png(colour, size=(42, 59)):
    out = BytesIO()
    Image.new("RGBA", size, colour).save(out, "PNG")
    return out.getvalue()


def content_pdf(pages):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595.28, height=841.89)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def artwork(page):
    """Colour of the background image stamped on `page`."""
    images = [x.get_object() for x in page["/Resources"]["/XObject"].values()]
    images = [x for x in images if x.get("/Subtype") == "/Image"]
    return [x.get_data()[:3] for x in images]


FIRST, LATER = png((255, 0, 0, 255)), png((0, 0, 255, 128))


class TestProposalPdf(unittest.TestCase):
    def test_first_page_and_every_later_page_get_their_artwork_once(self):
        pdf = PdfReader(BytesIO(proposal_pdf.add_backgrounds(content_pdf(4), FIRST, LATER)))

        self.assertEqual(len(pdf.pages), 4)
        self.assertEqual(artwork(pdf.pages[0]), [b"\xff\x00\x00"])
        for page in pdf.pages[1:]:
            # half-transparent blue flattened onto white paper
            self.assertEqual(artwork(page), [b"\x7f\x7f\xff"])

    def test_password_is_applied_after_stamping(self):
        pdf = PdfReader(BytesIO(proposal_pdf.add_backgrounds(content_pdf(2), FIRST, LATER, "secret")))
        self.assertTrue(pdf.is_encrypted)
        pdf.decrypt("secret")
        self.assertEqual(len(pdf.pages), 2)

    @patch("frappe.utils.pdf.get_pdf")
    @patch.object(proposal_pdf, "read_public_file", side_effect=[FIRST, LATER])
    @patch("frappe.get_cached_value", return_value=proposal_pdf.DOCTYPE)
    def test_hook_renders_only_the_proposal_format(self, _doc_type, _read, wkhtmltopdf):
        wkhtmltopdf.return_value = content_pdf(1)

        for print_format, generator in (
            ("Standard", proposal_pdf.GENERATOR),
            (proposal_pdf.PRINT_FORMAT, "wkhtmltopdf"),
            (proposal_pdf.PRINT_FORMAT, "chrome"),
        ):
            self.assertIsNone(proposal_pdf.get_pdf(print_format, "<p>x</p>", {}, None, generator))
        wkhtmltopdf.assert_not_called()

        options = {"password": "secret", "margin-top": "60mm"}
        pdf = proposal_pdf.get_pdf(proposal_pdf.PRINT_FORMAT, "<p>x</p>", options, None, proposal_pdf.GENERATOR)
        # password is kept from wkhtmltopdf and applied to the stamped file instead
        self.assertEqual(wkhtmltopdf.call_args.kwargs["options"], {"margin-top": "60mm"})
        self.assertTrue(PdfReader(BytesIO(pdf)).is_encrypted)

    @patch("frappe.get_cached_value", return_value="Sales Invoice")
    def test_hook_ignores_the_format_name_on_another_doctype(self, _doc_type):
        self.assertIsNone(
            proposal_pdf.get_pdf(proposal_pdf.PRINT_FORMAT, "<p>x</p>", {}, None, proposal_pdf.GENERATOR)
        )

    @patch("frappe.utils.pdf.get_pdf", return_value=content_pdf(3))
    @patch.object(proposal_pdf, "read_public_file", side_effect=[FIRST, LATER])
    @patch("frappe.get_cached_value", return_value=proposal_pdf.DOCTYPE)
    def test_multi_pdf_output_is_appended(self, *_):
        output = PdfWriter()
        output.add_blank_page(width=10, height=10)
        result = proposal_pdf.get_pdf(proposal_pdf.PRINT_FORMAT, "<p>x</p>", {}, output, proposal_pdf.GENERATOR)
        self.assertIs(result, output)
        self.assertEqual(len(output.pages), 4)

    def test_page_labels_are_stamped_from_their_first_page(self):
        label = proposal_pdf.PageLabel("Page {page} of {total}", (266.6, 266.6), first_page=2, bold_numbers=True)
        pdf = PdfReader(BytesIO(proposal_pdf.add_backgrounds(content_pdf(3), None, None, label=label)))

        self.assertEqual([page.extract_text().strip() for page in pdf.pages], ["", "Page 2 of 3", "Page 3 of 3"])
        # no artwork requested, none embedded
        self.assertNotIn("/XObject", pdf.pages[1]["/Resources"])

    @patch("frappe.utils.pdf.get_pdf", return_value=content_pdf(5))
    @patch.object(proposal_pdf, "read_public_file", side_effect=[FIRST, LATER])
    @patch("frappe.get_cached_value", return_value="Customer Vendor Agreement")
    def test_vendor_agreement_gets_artwork_and_page_numbers(self, *_):
        pdf = PdfReader(BytesIO(proposal_pdf.get_pdf(
            "Customer Vendor Agreement", "<p>x</p>", {}, None, proposal_pdf.GENERATOR)))

        self.assertEqual(artwork(pdf.pages[0]), [b"\xff\x00\x00"])
        self.assertEqual(artwork(pdf.pages[4]), [b"\x7f\x7f\xff"])
        self.assertEqual(pdf.pages[0].extract_text().strip(), "1 of 5")

    @patch("frappe.utils.pdf.get_pdf", return_value=content_pdf(4))
    @patch.object(proposal_pdf, "read_public_file")
    @patch("frappe.get_cached_value", return_value="Customer KSEB Agreement")
    def test_kseb_agreement_needs_no_artwork(self, _doc_type, read, _wkhtmltopdf):
        pdf = PdfReader(BytesIO(proposal_pdf.get_pdf(
            "Customer KSEB Agreement", "<p>x</p>", {}, None, proposal_pdf.GENERATOR)))

        read.assert_not_called()
        self.assertEqual(pdf.pages[3].extract_text().strip(), "Page 4 of 4")

    @patch("frappe.utils.pdf.get_pdf")
    @patch("frappe.get_cached_value", return_value=proposal_pdf.DOCTYPE)
    def test_missing_artwork_stops_generation(self, _doc_type, wkhtmltopdf):
        with patch("frappe.get_site_path", return_value="/nonexistent/proposal_bg.png"), \
            patch.object(proposal_pdf, "_", side_effect=lambda message: message), \
            patch("frappe.throw", side_effect=ValueError) as throw:
            with self.assertRaises(ValueError):
                proposal_pdf.get_pdf(proposal_pdf.PRINT_FORMAT, "<p>x</p>", {}, None, proposal_pdf.GENERATOR)
        self.assertIn("/files/proposal_fp_bg.png", throw.call_args.args[0])
        wkhtmltopdf.assert_not_called()
