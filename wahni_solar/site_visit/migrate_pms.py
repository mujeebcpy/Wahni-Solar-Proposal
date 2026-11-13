"""Explicit, repeatable legacy copy. Never runs automatically during bench migrate."""

from pathlib import Path

import frappe
from frappe.utils import cint

SOURCE = "Site Data Collection"
TARGET = "PMS Visit"
LEGACY_FIELDS = (
    "pms_date", "service_person_name", "client_name", "place", "plant_capacity_kw",
    "ac_db_string_inverter", "inverter_name_plate", "ac_db", "dc_db", "panel_image",
    "house_image", "additional_image", "site_location_link", "inspection_remarks", "customer",
)
PHOTO_FIELDS = (
    "ac_db_string_inverter", "inverter_name_plate", "ac_db", "dc_db", "panel_image", "house_image", "additional_image",
)
AUDIT_FIELDS = ("owner", "creation", "modified", "modified_by")


def attachments_for(row):
    """Include timeline attachments and image fields, even if originally unattached."""
    names = set(frappe.get_all("File", filters={
        "attached_to_doctype": SOURCE, "attached_to_name": row.name, "is_folder": 0,
    }, pluck="name"))
    for field in PHOTO_FIELDS:
        url = row.get(field)
        if not url:
            continue
        name = frappe.db.get_value("File", {"file_url": url, "is_folder": 0}, "name")
        if name:
            names.add(name)
        elif url.startswith("/"):
            raise ValueError(f"{field}: no File record exists for {url}")
    files = [frappe.get_doc("File", name) for name in sorted(names)]
    for file in files:
        if file.file_url and file.file_url.startswith("/") and not Path(file.get_full_path()).is_file():
            raise ValueError(f"Attachment is missing from disk: {file.file_name}")
    return files


def migrate(dry_run=True):
    """Preview by default; dry_run=0 copies with original IDs, photos and audit dates.

    Old records and original File records are retained, including their privacy.
    New attachment records reuse the files instead of moving or deleting blobs.
    """
    frappe.only_for("System Manager")
    dry_run = bool(cint(dry_run))
    report = {"dry_run": dry_run, "source_total": 0, "ready": 0, "already_copied": 0, "copied": 0, "errors": []}
    if not frappe.db.exists("DocType", SOURCE):
        return {**report, "message": "Site Data Collection does not exist on this site; nothing to copy."}
    if not frappe.db.exists("DocType", TARGET):
        frappe.throw("Install the PMS Visit DocType with bench migrate before copying legacy reports.")
    source_meta = frappe.get_meta(SOURCE)
    fields = [field for field in LEGACY_FIELDS if source_meta.has_field(field)]
    rows = frappe.get_all(SOURCE, fields=["name", *fields, *AUDIT_FIELDS], order_by="creation asc")
    report["source_total"] = len(rows)
    required = [df.fieldname for df in frappe.get_meta(TARGET).fields if df.reqd and df.fieldname in LEGACY_FIELDS]
    ready = []
    for row in rows:
        if frappe.db.exists(TARGET, {"legacy_site_data_collection": row.name}):
            report["already_copied"] += 1
            continue
        if frappe.db.exists(TARGET, row.name):
            report["errors"].append({"name": row.name, "reason": "An unrelated PMS Visit already uses this name."})
            continue
        missing = [field for field in required if row.get(field) in (None, "")]
        if not (row.get("service_person_name") or "").strip():
            missing.append("service_person_name")
        if not row.get("customer") and not (row.get("client_name") or "").strip():
            missing.append("customer or client_name")
        if missing:
            report["errors"].append({"name": row.name, "reason": "Missing required legacy fields: " + ", ".join(missing)})
            continue
        try:
            attachments_for(row)
        except ValueError as error:
            report["errors"].append({"name": row.name, "reason": str(error)})
            continue
        ready.append(row)
    report["ready"] = len(ready)
    if dry_run:
        return report
    if report["errors"]:
        frappe.throw("Legacy PMS preflight failed. Run with dry_run=1 and resolve the reported errors; nothing was copied.")

    frappe.db.savepoint("legacy_pms_copy")
    previous_flag = frappe.flags.get("in_legacy_pms_import")
    frappe.flags.in_legacy_pms_import = True
    try:
        for row in ready:
            files = attachments_for(row)
            photos = {field: row.get(field) for field in PHOTO_FIELDS}
            visit = frappe.get_doc({
                "doctype": TARGET,
                **{field: row.get(field) for field in fields if field not in PHOTO_FIELDS},
                "legacy_site_data_collection": row.name,
            })
            # Do not let Frappe's automatic Attach hook claim an old, unattached
            # File. Insert inside this transaction, add dedicated references,
            # then save the complete report with normal mandatory validation.
            visit.insert(ignore_permissions=True, ignore_mandatory=True, set_name=row.name)
            copied = set()
            for source_file in files:
                file_fields = [field for field, url in photos.items() if url == source_file.file_url] or [None]
                for field in file_fields:
                    key = (source_file.file_url, field)
                    if key in copied:
                        continue
                    attachment = frappe.copy_doc(source_file)
                    attachment.update({"attached_to_doctype": TARGET, "attached_to_name": visit.name,
                                       "attached_to_field": field})
                    attachment.flags.copy_from_existing_file = True
                    attachment.insert(ignore_permissions=True)
                    copied.add(key)
            visit.update(photos)
            visit.flags.ignore_mandatory = False
            visit.save(ignore_permissions=True)
            frappe.db.set_value(TARGET, visit.name, {field: row.get(field) for field in AUDIT_FIELDS}, update_modified=False)
            report["copied"] += 1
    except Exception:
        frappe.db.rollback(save_point="legacy_pms_copy")
        raise
    finally:
        frappe.flags.in_legacy_pms_import = previous_flag
    return report
