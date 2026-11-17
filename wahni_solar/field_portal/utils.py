"""Helpers shared by the Wahni Field document APIs."""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime

IDEMPOTENCY_TTL = 24 * 60 * 60


def parse(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            frappe.throw(_("Invalid request data."))
    return value or {}


def idempotent_insert(token, build):
    """Insert once per client token, so a retried request after an uncertain
    network failure returns the first record instead of creating a duplicate."""
    if not token:
        return build().insert()
    key = f"wahni_field:create:{frappe.session.user}:{token}"
    existing = frappe.cache.get_value(key)
    if existing and frappe.db.exists(existing["doctype"], existing["name"]):
        return frappe.get_doc(existing["doctype"], existing["name"])
    doc = build().insert()
    frappe.cache.set_value(key, {"doctype": doc.doctype, "name": doc.name}, expires_in_sec=IDEMPOTENCY_TTL)
    return doc


def ensure_not_stale(doc, modified):
    """Refuse to overwrite a newer version saved elsewhere (e.g. in Desk)."""
    if modified and get_datetime(modified) != get_datetime(doc.modified):
        frappe.throw(
            _("This record was changed by someone else. Reload to see the latest version; your edits are still on screen."),
            frappe.TimestampMismatchError,
        )


def attachments(doc):
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_folder": 0},
        fields=["name", "file_name", "file_url", "is_private", "file_size", "attached_to_field", "creation"],
        order_by="creation asc",
    )
    return [file for file in files if frappe.has_permission("File", "read", doc=file.name)]


def remove_attachment(doc, file_name):
    """Delete a file attached to this document (never a file referenced elsewhere)."""
    file = frappe.get_doc("File", file_name)
    if file.attached_to_doctype != doc.doctype or file.attached_to_name != doc.name:
        frappe.throw(_("This file does not belong to the record."), frappe.PermissionError)
    doc.check_permission("write")
    file.delete()
