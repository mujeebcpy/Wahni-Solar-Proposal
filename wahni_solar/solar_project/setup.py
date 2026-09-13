"""Idempotent install/migrate setup. Existing library uploads are never replaced."""

import json
from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils.file_manager import save_file


def after_migrate():
    create_custom_fields({"Project": [
        {"fieldname": "custom_project_report_section", "fieldtype": "Section Break",
         "label": "Project Report", "insert_after": "custom_cost_breakdown", "module": "Solar Project"},
        {"fieldname": "custom_report_grid_check", "fieldtype": "Link", "label": "Report KSEB Grid Check",
         "options": "KSEB Grid Check", "insert_after": "custom_project_report_section", "module": "Solar Project",
         "description": "Optional when the customer's Lead has exactly one Grid Check."},
        {"fieldname": "custom_report_sales_invoice", "fieldtype": "Link", "label": "Report Sales Invoice",
         "options": "Sales Invoice", "insert_after": "custom_report_grid_check", "module": "Solar Project",
         "description": "Optional. A sole matching submitted invoice is selected automatically."},
        {"fieldname": "custom_panel_watt_peak", "fieldtype": "Int", "label": "Panel Watt Peak (Wp)",
         "non_negative": 1, "insert_after": "custom_report_sales_invoice", "module": "Solar Project",
         "description": "Individual panel rating, e.g. 600 or 630. Combined panel datasheet/BIS selection uses this value and the linked Solar Proposal's panel brand."},
        {"fieldname": "custom_report_attachments", "fieldtype": "Table", "label": "Report Documents",
         "options": "Project Report Attachment", "insert_after": "custom_panel_watt_peak",
         "module": "Solar Project", "description": "Labelled PDF uploads override automatic documents of the same category."},
        {"fieldname": "custom_latest_project_report", "fieldtype": "Link", "label": "Latest Project Report",
         "options": "Project Report", "read_only": 1, "no_copy": 1,
         "insert_after": "custom_report_attachments", "module": "Solar Project"},
        {"fieldname": "custom_project_report_status", "fieldtype": "Data", "label": "Report Status",
         "read_only": 1, "no_copy": 1, "insert_after": "custom_latest_project_report", "module": "Solar Project"},
    ]})
    # The proposal module exports a Project field_order setter; merge rather than replace it.
    order = frappe.get_meta("Project").get("field_order")
    if order:
        order = json.loads(order) if isinstance(order, str) else list(order)
        additions = ["custom_project_report_section", "custom_report_grid_check", "custom_report_sales_invoice",
                     "custom_panel_watt_peak", "custom_report_attachments", "custom_latest_project_report", "custom_project_report_status"]
        order = [field for field in order if field not in additions]
        index = order.index("custom_cost_breakdown") + 1 if "custom_cost_breakdown" in order else len(order)
        order[index:index] = additions
        make_property_setter("Project", None, "field_order", json.dumps(order), "Data", for_doctype=True)
    seed_library()


def seed_library():
    folder = Path(frappe.get_app_path("wahni_solar", "solar_project", "templates"))
    entries = [
        ("Default Checklist", "Check List", "", "Check_List_Fillable.pdf", 0, 0),
        ("Default Completion Certificate", "Project Completion Report", "", "Completion_Certificate_Fillable.pdf", 0, 0),
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
