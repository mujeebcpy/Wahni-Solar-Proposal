"""Page artwork for Wahni-branded PDFs (Solar Proposal, Customer Vendor Agreement).

Frappe renders these Print Formats with wkhtmltopdf as usual (standard
Print → PDF button, emails, attachments). This `pdf_generator` hook then stamps
PNG artwork under the paginated result: the first-page PNG behind page 1 and the
later-page PNG behind every later page, scaled to the full page, plus optional
"N of M" page labels. CSS can't do this: wkhtmltopdf paints backgrounds only
inside the page margins, and a footer-html would inherit the format's margins.

Frappe calls `pdf_generator` hooks only when the Print Format's PDF Generator is
not plain "wkhtmltopdf", so setup() adds GENERATOR as an option and selects it
on the proposal format (the other formats ship with it in their JSON). Any other
format, or this generator on any other format, falls through to Frappe's
standard wkhtmltopdf output.
"""

import os
import zlib
from string import Formatter
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

import frappe
from frappe import _
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

DOCTYPE = "Solar Proposal"
PRINT_FORMAT = "Solar Proposal"
GENERATOR = "wkhtmltopdf + proposal artwork"
# public files of the current site, i.e. /files/<name>
FIRST_PAGE_BG = "proposal_fp_bg.png"
LATER_PAGE_BG = "proposal_bg.png"

# removed: the previous per-format "Page Background (PDF)" generator
OLD_GENERATOR = "wkhtmltopdf + background"
OLD_FIELD = "custom_page_background"

MM = 72 / 25.4


@dataclass(frozen=True)
class PageLabel:
    """Centred page label in Times 12pt, e.g. "{page} of {total}"."""

    template: str
    # baseline, in mm from the top edge, on the first page and on later pages
    baseline_mm: tuple
    first_page: int = 1
    bold_numbers: bool = False
    size: float = 12


@dataclass(frozen=True)
class Artwork:
    doctype: str
    first_bg: str | None = None
    later_bg: str | None = None
    label: PageLabel | None = None


# print format -> what gets stamped on its PDF
FORMATS = {
    PRINT_FORMAT: Artwork(DOCTYPE, FIRST_PAGE_BG, LATER_PAGE_BG),
    # positions measured from the signed paper originals
    "Customer Vendor Agreement": Artwork(
        "Customer Vendor Agreement", FIRST_PAGE_BG, LATER_PAGE_BG, PageLabel("{page} of {total}", (270.5, 276.5))
    ),
    "Customer KSEB Agreement": Artwork(
        "Customer KSEB Agreement",
        label=PageLabel("Page {page} of {total}", (266.6, 266.6), first_page=2, bold_numbers=True),
    ),
}


def get_pdf(print_format=None, html=None, options=None, output=None, pdf_generator=None):
    """`pdf_generator` hook: return None to let Frappe fall back to plain wkhtmltopdf."""
    artwork = FORMATS.get(print_format)
    if pdf_generator != GENERATOR or not artwork:
        return None
    if frappe.get_cached_value("Print Format", print_format, "doc_type") != artwork.doctype:
        return None

    from frappe.utils.pdf import get_pdf as wkhtmltopdf

    # fail before rendering if the artwork is missing
    first = read_public_file(artwork.first_bg) if artwork.first_bg else None
    later = read_public_file(artwork.later_bg) if artwork.later_bg else None

    options = dict(options or {})
    # encrypt after stamping; an encrypted PDF can't be modified
    password = options.pop("password", None)

    pdf = add_backgrounds(wkhtmltopdf(html, options=options), first, later, password, artwork.label)

    if output is not None:
        output.append(PdfReader(BytesIO(pdf)))
        return output

    return pdf


def add_backgrounds(pdf, first_png, later_png, password=None, label=None):
    """Put `first_png` behind page 1 and `later_png` behind every other page, edge to edge,
    and `label` over each page from `label.first_page` on."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))
    total = len(writer.pages)

    for index, page in enumerate(writer.pages):
        box = tuple(float(x) for x in page.mediabox)
        png = first_png if index == 0 else later_png
        if png:
            # a fresh background page per merge, so nothing carries over between pages
            background = PdfReader(BytesIO(background_pdf(png, box))).pages[0]
            page.merge_page(background, over=False)
        if label and index + 1 >= label.first_page:
            page.merge_page(PdfReader(BytesIO(label_pdf(label, index + 1, total, box))).pages[0])

    # every later page embeds the same image; keep one copy
    writer.compress_identical_objects()

    if password:
        writer.encrypt(password)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


@lru_cache(maxsize=8)
def background_pdf(png, box):
    """One-page PDF of size `box` (x0, y0, x1, y1 in pt) with the PNG stretched over it."""
    x0, y0, x1, y1 = box

    with Image.open(BytesIO(png)) as source:
        rgba = source.convert("RGBA")
    # flatten transparency onto white (the paper colour), losslessly
    image = Image.new("RGB", rgba.size, "white")
    image.paste(rgba, mask=rgba.getchannel("A"))

    writer = PdfWriter()
    page = writer.add_blank_page(width=x1 - x0, height=y1 - y0)
    page.mediabox.lower_left = (x0, y0)
    page.mediabox.upper_right = (x1, y1)

    xobject = DecodedStreamObject()
    xobject.set_data(zlib.compress(image.tobytes()))
    xobject.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(image.width),
        NameObject("/Height"): NumberObject(image.height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/FlateDecode"),
    })

    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/ProposalBg"): writer._add_object(xobject)}),
        NameObject("/ProcSet"): ArrayObject([NameObject("/PDF"), NameObject("/ImageC")]),
    })
    content = DecodedStreamObject()
    content.set_data(f"q {x1 - x0:.4f} 0 0 {y1 - y0:.4f} {x0:.4f} {y0:.4f} cm /ProposalBg Do Q".encode())
    page[NameObject("/Contents")] = writer._add_object(content)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# Adobe standard-14 advance widths (1/1000 em) for the characters page labels use
TIMES_WIDTHS = {" ": 250, "P": 556, "a": 444, "g": 500, "e": 444, "o": 500, "f": 333, **dict.fromkeys("0123456789", 500)}


def label_pdf(label, page_number, total, box):
    """One transparent page of size `box` carrying `label` centred at its baseline."""
    x0, y0, x1, y1 = box
    runs = []  # (font, text)
    for literal, field, _spec, _conv in Formatter().parse(label.template):
        if literal:
            runs.append(("/F1", literal))
        if field:
            runs.append(("/F2" if label.bold_numbers else "/F1", str({"page": page_number, "total": total}[field])))

    width = sum(TIMES_WIDTHS.get(c, 500) for _font, text in runs for c in text) * label.size / 1000
    x = x0 + (x1 - x0 - width) / 2
    baseline_mm = label.baseline_mm[0 if page_number == 1 else 1]
    y = y1 - baseline_mm * MM

    ops = [f"BT 0 g {x:.2f} {y:.2f} Td"]
    for font, text in runs:
        ops.append(f"{font} {label.size} Tf ({text}) Tj")
    ops.append("ET")

    writer = PdfWriter()
    page = writer.add_blank_page(width=x1 - x0, height=y1 - y0)
    page.mediabox.lower_left = (x0, y0)
    page.mediabox.upper_right = (x1, y1)

    def font(name):
        return writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject(name),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }))

    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): font("/Times-Roman"), NameObject("/F2"): font("/Times-Bold"),
        }),
    })
    content = DecodedStreamObject()
    content.set_data(" ".join(ops).encode())
    page[NameObject("/Contents")] = writer._add_object(content)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def read_public_file(file_name):
    """Read /files/<file_name> from this site's public folder (never over HTTP)."""
    path = frappe.get_site_path("public", "files", file_name)
    if not os.path.isfile(path):
        frappe.throw(
            _("PDF background {0} is missing. Upload it as a public file named {1}.").format(
                f"/files/{file_name}", file_name
            ),
            title=_("Missing PDF Background"),
        )
    with open(path, "rb") as f:
        return f.read()


def setup():
    """Idempotent (after_migrate): register GENERATOR, select it on PRINT_FORMAT and
    remove the old "wkhtmltopdf + background" generator's option and custom field."""
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    current = (frappe.get_meta("Print Format").get_options("pdf_generator") or "wkhtmltopdf").split("\n")
    options = [o for o in current if o != OLD_GENERATOR]
    if GENERATOR not in options:
        options.append(GENERATOR)
    if options != current:
        make_property_setter(
            "Print Format", "pdf_generator", "options", "\n".join(options), "Text",
            validate_fields_for_doctype=False,
        )

    # formats still on the removed generator go back to plain wkhtmltopdf
    for name in frappe.get_all("Print Format", filters={"pdf_generator": OLD_GENERATOR}, pluck="name"):
        frappe.db.set_value("Print Format", name, "pdf_generator", "wkhtmltopdf", update_modified=False)

    if frappe.db.exists("Print Format", PRINT_FORMAT) and GENERATOR not in current:
        # first migrate after this generator was added; later changes to the format are left alone
        frappe.db.set_value("Print Format", PRINT_FORMAT, "pdf_generator", GENERATOR, update_modified=False)

    if field := frappe.db.exists("Custom Field", {"dt": "Print Format", "fieldname": OLD_FIELD}):
        frappe.delete_doc("Custom Field", field, ignore_permissions=True)

    frappe.clear_cache(doctype="Print Format")
