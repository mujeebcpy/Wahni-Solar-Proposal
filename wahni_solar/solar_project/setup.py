"""Idempotent install/migrate setup. Existing library uploads are never replaced."""

from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file


def after_migrate():
    from wahni_solar.solar_project.equipment import migrate_package_brands
    from wahni_solar.wahni_solar_proposal import pdf_background

    migrate_package_brands()
    seed_library()
    pdf_background.setup()

def seed_library():
    folder = Path(frappe.get_app_path("wahni_solar", "solar_project", "templates"))
    entries = [
        ("Default Checklist", "Check List", "", "Check_List_Fillable.pdf", 0, 0),
        ("Default Completion Certificate", "Project Completion Report", "", "Completion_Certificate_Fillable.pdf", 0, 0),
        ("Default KSEB Agreement", "KSEB Agreement", "", "KSEB_Agreement_Fillable.pdf", 0, 0),
        ("Default Customer Vendor Agreement", "Customer Vendor Agreement", "", "Solar_Customer_Vendor_Agreement_Fillable.pdf", 0, 0),
        ("Enphase Datasheet", "Inverter Datasheet", "Enphase", "16.IQ8P Microinverter n BIS.pdf", 1, 4),
        ("Enphase BIS", "Inverter BIS", "Enphase", "16.IQ8P Microinverter n BIS.pdf", 5, 6),
        ("Vsole Datasheet", "Inverter Datasheet", "Vsole", "Vsole_Micro Inverter_Datasheet n BIS.pdf", 1, 1),
        ("Vsole BIS", "Inverter BIS", "Vsole", "Vsole_Micro Inverter_Datasheet n BIS.pdf", 2, 2),
        ("Default SPD", "ACDB SPD Datasheet", "", "19.SPD_Citel_1Ph.pdf", 0, 0),
        ("Default MCB", "ACDB MCB Datasheet", "", "MCB_ABB.pdf", 0, 0),
        ("Default Earthing", "Earth Kit Datasheets", "", "Earthing.pdf", 0, 0),
        ("Enphase SLD", "SLD Template", "Enphase", "SLD_Enphase.qet", 0, 0),
        ("Vsole SLD", "SLD Template", "Vsole", "SLD_vsole.qet", 0, 0),
    ]
    for title, category, brand, filename, start, end in entries:
        if frappe.db.exists("Project Report Document", title):
            continue
        source = folder / filename
        if not source.is_file():
            continue
        doc = frappe.get_doc({"doctype": "Project Report Document", "title": title,
                              "category": category, "brand": brand, "enabled": 1,
                              "page_from": start, "page_to": end})
        # The document name is known before insertion; attach the seed as a private File.
        file = save_file(filename, source.read_bytes(), None, None, is_private=1)
        doc.file = file.file_url
        doc.insert(ignore_permissions=True)
        file.db_set({"attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
                     "attached_to_field": "file"})
