"""Remove archived legacy configuration only when business records do not use it."""

import json
import os
import tempfile
from pathlib import Path

import frappe
from frappe.model.dynamic_links import get_dynamic_links
from frappe.model.rename_doc import get_link_fields
from frappe.utils import now_datetime

from wahni_solar.wahni_solar_proposal.upgrade import ARCHIVE_NAME, _read_archive

# Frappe removes these administrative references during normal document deletion.
# Business documents are always checked, regardless of ignore_links_on_delete hooks.
ADMINISTRATIVE_REFERENCES = {
    "Communication", "ToDo", "Comment", "Version", "DocShare", "View Log",
    "Notification Log", "Activity Log", "Access Log", "Document Follow", "User Permission",
}


def dependencies(doc):
    """Inspect static/custom/dynamic references, including cancelled parent records."""
    references = set()

    def inspect(source, filters):
        meta = frappe.get_meta(source)
        if meta.is_virtual:
            return
        if meta.issingle:
            if all(frappe.db.get_single_value(source, key) == value for key, value in filters.items()):
                if source not in ADMINISTRATIVE_REFERENCES and (source, source) != (doc.doctype, doc.name):
                    references.add((source, source))
            return
        if source in ADMINISTRATIVE_REFERENCES and not meta.istable:
            return
        fields = ["name", "parent", "parenttype"] if meta.istable else ["name"]
        for row in frappe.get_all(source, filters=filters, fields=fields, limit_page_length=0):
            target = (row["parenttype"], row["parent"]) if meta.istable else (source, row["name"])
            if target[0] not in ADMINISTRATIVE_REFERENCES and target != (doc.doctype, doc.name):
                references.add(target)

    for field in get_link_fields(doc.doctype):
        inspect(field["parent"], {field["fieldname"]: doc.name})
    # The cached dynamic-link map can miss target types. Raw field metadata also
    # avoids the ordinary delete checks' exclusion of cancelled transactions.
    for field in get_dynamic_links():
        inspect(field["parent"], {field["options"]: doc.doctype, field["fieldname"]: doc.name})
    # Normal delete_doc removes attachments too. Keep staff uploads in place.
    for row in frappe.get_all("File", filters={"attached_to_doctype": doc.doctype,
                             "attached_to_name": doc.name}, fields=["name"], limit_page_length=0):
        references.add(("File", row["name"]))
    return [{"doctype": doctype, "name": name} for doctype, name in sorted(references)]


def _archive_documents(documents):
    """Write complete current documents, including charges, before any deletion."""
    directory = Path(frappe.get_site_path("private", "backups"))
    directory.mkdir(parents=True, exist_ok=True)
    handle, filename = tempfile.mkstemp(prefix="wahni-solar-legacy-cleanup-", suffix=".json", dir=directory)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump({
                "archive_version": 1, "site": frappe.local.site, "created_on": str(now_datetime()),
                "original_archive": ARCHIVE_NAME,
                "documents": [doc.as_dict() for doc in documents],
            }, stream, indent=2, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(filename)
        raise
    return filename


def cleanup_unused_legacy_configuration():
    """One-time post-sync cleanup; never force deletion or touch new templates."""
    original = _read_archive()
    if original is None:
        raise ValueError("The original solar legacy configuration archive is missing; cleanup stopped.")
    report = {"deleted": [], "retained": [], "archive": None}
    documents = []
    for doctype, key in (("Solar Proposal", "proposals"), ("Solar Package", "packages")):
        for name in sorted({row["name"] for row in original[key]}):
            if not frappe.db.exists(doctype, name):
                continue
            doc = frappe.get_doc(doctype, name)
            if doctype == "Solar Proposal" and doc.get("calculation_version") != "Legacy":
                report["retained"].append({"doctype": doctype, "name": name, "reason": "Converted to template rules."})
            elif doctype == "Solar Package" and (doc.get("component_rules") or doc.get("input_definitions") or doc.get("is_demo")):
                report["retained"].append({"doctype": doctype, "name": name, "reason": "Used by the new configuration."})
            else:
                documents.append(doc)
    if not documents:
        return report
    report["archive"] = _archive_documents(documents)
    # Proposals are removed first; package links are then checked against the
    # remaining proposals, Projects and all other business documents.
    for doc in documents:
        references = dependencies(doc)
        if references:
            report["retained"].append({"doctype": doc.doctype, "name": doc.name,
                                       "reason": "Referenced by another record or attachment.", "references": references})
            continue
        if doc.get("docstatus") == 1:
            report["retained"].append({"doctype": doc.doctype, "name": doc.name, "reason": "Submitted record."})
            continue
        frappe.db.savepoint("solar_legacy_cleanup")
        try:
            frappe.delete_doc(doc.doctype, doc.name, ignore_permissions=True)
        except frappe.LinkExistsError:
            # on_trash hooks run before Frappe's final link checks.
            frappe.db.rollback(save_point="solar_legacy_cleanup")
            frappe.clear_messages()
            report["retained"].append({"doctype": doc.doctype, "name": doc.name, "reason": "Referenced by another record."})
        else:
            report["deleted"].append({"doctype": doc.doctype, "name": doc.name})
    return report
