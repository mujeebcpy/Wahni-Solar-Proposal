"""PDF generator that lays a full-page background under every page.

wkhtmltopdf can only paint CSS backgrounds inside the page margins and only
as far as the content goes, so the background is stamped onto the finished
PDF instead: page 1 of the Print Format's "Page Background (PDF)" is scaled
to each page and placed underneath it, edge to edge.

Enabled per Print Format by setting PDF Generator to GENERATOR.
"""

import os
from io import BytesIO

import frappe
from pypdf import PdfReader, PdfWriter, Transformation

GENERATOR = "wkhtmltopdf + background"
BACKGROUND_FIELD = "custom_page_background"


def get_pdf(print_format=None, html=None, options=None, output=None, pdf_generator=None):
    """`pdf_generator` hook: return None to let Frappe fall back to other generators."""
    if pdf_generator != GENERATOR:
        return None

    from frappe.utils.pdf import get_pdf as wkhtmltopdf

    options = dict(options or {})
    # encrypt after stamping; an encrypted PDF can't be modified
    password = options.pop("password", None)

    pdf = wkhtmltopdf(html, options=options)

    background_url = print_format and frappe.get_cached_value("Print Format", print_format, BACKGROUND_FIELD)
    if background_url or password:
        pdf = add_background(pdf, read_file(background_url) if background_url else None, password)

    if output:
        output.append(PdfReader(BytesIO(pdf)))
        return output

    return pdf


def add_background(pdf, background=None, password=None):
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))

    if background:
        bg_page = PdfReader(BytesIO(background)).pages[0]
        bg_width, bg_height = float(bg_page.mediabox.width), float(bg_page.mediabox.height)

        for page in writer.pages:
            scale = Transformation().scale(
                float(page.mediabox.width) / bg_width, float(page.mediabox.height) / bg_height
            )
            page.merge_transformed_page(bg_page, scale, over=False)

    if password:
        writer.encrypt(password)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def setup():
    """Idempotent (after_migrate): add the generator option and background field to Print Format."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    options = (frappe.get_meta("Print Format").get_options("pdf_generator") or "wkhtmltopdf").split("\n")
    if GENERATOR not in options:
        make_property_setter(
            "Print Format", "pdf_generator", "options", "\n".join([*options, GENERATOR]), "Text",
            validate_fields_for_doctype=False,
        )

    if not frappe.db.exists("Custom Field", {"dt": "Print Format", "fieldname": BACKGROUND_FIELD}):
        create_custom_field("Print Format", {
            "fieldname": BACKGROUND_FIELD,
            "label": "Page Background (PDF)",
            "fieldtype": "Attach",
            "insert_after": "pdf_generator",
            "depends_on": f'eval:doc.pdf_generator=="{GENERATOR}"',
            "description": "A4 PDF; page 1 is placed full-bleed under every page of the generated PDF.",
        })

    # the standard Solar Proposal format ships with its background
    if frappe.db.exists("Print Format", "Solar Proposal") and not frappe.db.get_value(
        "Print Format", "Solar Proposal", BACKGROUND_FIELD
    ):
        frappe.db.set_value("Print Format", "Solar Proposal", {
            "pdf_generator": GENERATOR,
            BACKGROUND_FIELD: "/assets/wahni_solar/images/proposal_bg.pdf",
        }, update_modified=False)


def read_file(file_url):
    if file_url.startswith("/assets/"):
        # app assets, e.g. /assets/wahni_solar/images/proposal_bg.pdf (no "..")
        relative = os.path.normpath(file_url).lstrip("/")
        path = os.path.join(frappe.local.sites_path, relative)
        if not relative.startswith("assets/") or not os.path.isfile(path):
            frappe.throw(frappe._("Page background {0} was not found").format(file_url))
        with open(path, "rb") as f:
            return f.read()

    file_name = frappe.db.get_value("File", {"file_url": file_url})
    if not file_name:
        frappe.throw(frappe._("Page background {0} was not found").format(file_url))
    return frappe.get_doc("File", file_name).get_content()
