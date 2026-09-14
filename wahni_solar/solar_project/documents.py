"""PDF and QET operations without database or filesystem side effects."""

import re
import xml.etree.ElementTree as ET
from datetime import date
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject


def text(value):
    return "" if value is None else str(value).strip()


def phase(value):
    value = text(value).lower()
    if value in {"3", "three", "three phase", "3 phase", "lt-1/three"}:
        return "3 Phase"
    if value in {"1", "single", "one", "single phase", "1 phase", "lt-1/single"}:
        return "1 Phase"
    return ""


def kw(value):
    try:
        number = float(value)
        return f"{number:g}kW" if number > 0 else ""
    except (TypeError, ValueError):
        return ""


def form_values(context):
    grid = context.get("grid") or {}
    lead = context.get("lead") or {}
    proposal = context.get("proposal") or {}
    package = context.get("package") or {}
    bank = context.get("bank") or {}
    phone = grid.get("registered_mobile") or lead.get("mobile_no")
    alternate = lead.get("mobile_no") if lead.get("mobile_no") != phone else lead.get("phone")
    checklist = {
        "electrical_division_and_sub_division": " / ".join(
            text(grid.get(key)) for key in ("division", "subdivision") if grid.get(key)
        ),
        "electrical_section": grid.get("section"),
        "consumer_number": grid.get("consumer_no"),
        "tariff": grid.get("tariff"),
        "connected_load": grid.get("connected_load"),
        "solar_plant_owner": grid.get("consumer_name"),
        "address": grid.get("customer_address"),
        "email_id": lead.get("email_id"),
        "consumer_contact_number": phone,
        "consumer_alternate_contact_number": alternate,
        "bank_account_holder_name": bank.get("account_name"),
        "bank_name": bank.get("bank"),
        "bank_ifsc_code": bank.get("branch_code"),
        "bank_account_number": bank.get("bank_account_no"),
        "supplier_installer_designer": "Wahni Green Technologies Pvt Ltd",
        "plant_type": package.get("grid_type"),
        "plant_total_capacity": kw(grid.get("proposed_solar_capacity")),
        "inverter_make_and_serial_number": package.get("brand"),
        "inverter_type": package.get("grid_type"),
        "voltage_and_number_of_phase": phase(grid.get("phase")),
    }
    # Proposal brand/count are known, but panel wattage and installed serials are not.
    panel_brand = proposal.get("panel_brand")
    if panel_brand and "/" not in panel_brand and proposal.get("panel_count"):
        checklist["pv_installations_make_and_total_number"] = (
            f"{panel_brand} - {proposal['panel_count']} nos"
        )
    completion = {
        "installation_owner_name": grid.get("consumer_name"),
        "installation_address": grid.get("customer_address"),
        "customer_name": grid.get("consumer_name"),
        "solar_panels": checklist.get("pv_installations_make_and_total_number"),
        "inverter_grid_tie": package.get("brand"),
        "voltage_and_supply_system": phase(grid.get("phase")),
    }
    return {
        "Check List": {key: text(value) for key, value in checklist.items()},
        "Project Completion Report": {key: text(value) for key, value in completion.items()},
        **agreement_values(context),
    }


def agreement_values(context):
    grid = context.get("grid") or {}
    customer = context.get("customer") or {}
    address = context.get("customer_address") or {}
    proposal = context.get("proposal") or {}
    panel = context.get("panel") or {}
    inverter = context.get("inverter") or {}
    # A locality alone is not a usable postal address.
    if text(address.get("address_line1")):
        postal_address = ", ".join(text(address.get(key)) for key in
                                   ("address_line1", "address_line2", "city", "county", "state", "country", "pincode")
                                   if text(address.get(key)))
        pincode = address.get("pincode")
    else:
        postal_address = text(grid.get("customer_address"))
        pins = re.findall(r"(?<!\d)\d{6}(?!\d)", postal_address)
        pincode = pins[0] if len(pins) == 1 else ""
    common = {
        "name": customer.get("customer_name") or grid.get("consumer_name"),
        "consumer_no": grid.get("consumer_no"),
        "customer_address": postal_address,
        "system_capacity": kw(proposal.get("capacity_kw")),
    }
    panel_capacity = ""
    try:
        watt_peak = float(panel.get("custom_panel_watt_peak"))
        if watt_peak > 0:
            panel_capacity = f"{watt_peak:g} Wp"
    except (TypeError, ValueError):
        pass
    kseb = {**common, "customer_pincode": pincode, "electrical_section": grid.get("section")}
    vendor = {
        **common,
        "applicant_name": common["name"],
        "applicant_address": postal_address,
        "solar_panel_make": panel.get("brand"),
        "solar_panel_model": panel.get("custom_model"),
        "solar_panel_capacity": panel_capacity,
        "inverter_make": inverter.get("brand"),
        "inverter_model": inverter.get("custom_model"),
        # The Item field has no specified unit; retain its entered rating.
        "inverter_capacity": inverter.get("custom_rated_capacity") or "",
        "system_price": proposal.get("project_cost"),
    }
    if context.get("generation_date"):
        generated_on = date.fromisoformat(context["generation_date"])
        kseb["agreement_date"] = str(generated_on.day)
        kseb["date_month_year"] = generated_on.strftime("%B %Y")
        vendor["date"] = generated_on.strftime("%d-%m-%Y")
    # Dates are editable; signing place is left for manual completion.
    return {category: {key: text(value) for key, value in values.items()}
            for category, values in (("KSEB Agreement", kseb), ("Customer Vendor Agreement", vendor))}


def read_pdf(content):
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported. Upload an unlocked PDF.")
    if not reader.pages:
        raise ValueError("The PDF has no pages.")
    return reader


def pdf_bytes(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def select_pdf_pages(content, page_from=None, page_to=None):
    reader = read_pdf(content)
    start = int(page_from or 1)
    end = int(page_to or len(reader.pages))
    if not 1 <= start <= end <= len(reader.pages):
        raise ValueError(f"Page range {start}–{end} is outside this {len(reader.pages)}-page PDF.")
    writer = PdfWriter()
    writer.append(reader, pages=(start - 1, end), import_outline=False)
    return pdf_bytes(writer)


def fill_form(content, values):
    reader = read_pdf(content)
    fields = reader.get_fields() or {}
    if not fields:
        raise ValueError("This template has no editable PDF form fields.")
    # Only supplied, non-empty values replace template data. All other current
    # values, defaults and appearances belong to the template and remain intact.
    mapped = {key: text(value) for key, value in values.items() if key in fields and text(value)}
    pending = [(field, "") for field in reader.trailer["/Root"]["/AcroForm"]["/Fields"]]
    visited = set()
    while pending:
        reference, parent_name = pending.pop()
        obj = reference.get_object()
        if id(obj) in visited:
            continue
        visited.add(id(obj))
        name = ".".join(part for part in (parent_name, text(obj.get("/T"))) if part)
        if name in mapped:
            # Resetting an updated field should retain the new customer's data.
            obj[NameObject("/DV")] = TextStringObject(mapped[name])
            obj.pop(NameObject("/RV"), None)
        if "/Kids" in obj:
            pending.extend((child, name) for child in obj["/Kids"])
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    # Passing individual pages also supports versions without the page=None shortcut.
    for page in writer.pages:
        if mapped and "/Annots" in page:
            writer.update_page_form_field_values(page, mapped, auto_regenerate=False)
    missing = [key for key, field in fields.items() if not text(mapped.get(key, field.get("/V")))]
    return pdf_bytes(writer), missing


def merge_pdfs(parts):
    """Preserve AcroForms and give every section an independent field namespace."""
    writer = PdfWriter()
    manifest = []
    for index, (category, content) in enumerate(parts):
        reader = read_pdf(content)
        if reader.get_fields():
            reader.add_form_topname(f"section_{index:02d}")
        start = len(writer.pages) + 1
        writer.append(reader, outline_item=category, import_outline=False)
        manifest.append({"category": category, "page_from": start, "page_to": len(writer.pages)})
    if not manifest:
        raise ValueError("No usable PDFs are available. Add report documents and try again.")
    return pdf_bytes(writer), manifest


def parse_qet(content):
    # ElementTree doesn't resolve external entities; also disallow internal DTD expansion.
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", content, re.I):
        raise ValueError("QET templates containing DTD/entity declarations are not supported.")
    root = ET.fromstring(content)
    if root.tag != "project" or not root.findall("diagram"):
        raise ValueError("Upload a QElectroTech project containing a diagram.")
    return root


def personalise_qet(content, context):
    root = parse_qet(content)
    grid, lead, proposal = (context.get(key) or {} for key in ("grid", "lead", "proposal"))
    package = context.get("package") or {}
    address = context.get("customer_address") or {}
    location = ", ".join(text(address.get(key)) for key in ("city", "county") if text(address.get(key)))
    location = location or text(grid.get("customer_address"))
    values = {
        "cstmr": text(grid.get("consumer_name")),
        "cnsnumb": text(grid.get("consumer_no")),
        "mbl": text(grid.get("registered_mobile") or lead.get("mobile_no")),
        "cntrdmd": kw(proposal.get("capacity_kw")),
        "plntcpt": kw(proposal.get("capacity_kw")),
        "cntype": phase(grid.get("phase")),
        "plntype": phase(package.get("connection_type")),
    }
    title = f"{values['plntcpt']} - {package.get('system_type') or 'Solar'}".strip()
    root.set("title", title)
    for diagram in root.findall("diagram"):
        diagram.set("title", title)
        diagram.set("locmach", location)
        properties = diagram.find("properties")
        if properties is None:
            properties = ET.SubElement(diagram, "properties")
        for key, value in values.items():
            prop = properties.find(f"property[@name='{key}']")
            if prop is None:
                prop = ET.SubElement(properties, "property", name=key, show="1")
            prop.text = value
    # Remove stale editor paths and file names stored by the template author.
    for prop in root.findall("./properties/property"):
        if prop.get("name") in {"savedfilename", "savedfilepath", "filename"}:
            prop.text = ""
    missing = [key for key, value in values.items() if not value]
    if not location:
        missing.append("location")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), missing
