"""One-time cleanup: delete generated documents that older releases attached to records.

Project documents, Project Reports and KSEB annexures are now generated on demand
and downloaded, so these stored copies only use disk space. Removed: generated
SLD/agreement/checklist/completion/report files on Project, input archives on
Project Report and Annexure I/II/III PDFs on KSEB Grid Check. Staff uploads
(Report Documents overrides, the shared library, any other attachment) are kept.

Preview on a site before migrating:

    bench --site SITE execute wahni_solar.patches.delete_generated_project_files.delete_generated_files --kwargs "{'dry_run': 1}"

Temporary: delete this file and its patches.txt line once it has run on every site.
"""

import re

import frappe

# save_file appends the last six characters of the content hash before the extension.
GENERATED = re.compile(
    r"^(?P<owner>.+)-(?P<kind>SLD|Customer-Vendor-Agreement|KSEB-Agreement|Check-List"
    r"|Project-Completion-Report|Project-Report|inputs)(?:[0-9a-f]{6})?\.(?P<ext>pdf|qet|zip)$"
)
ANNEXURE = re.compile(r"^Annexure-[123]-(?P<stem>.+)\.pdf$")
REPORT_NAME = re.compile(r"^SPR-\d{5,}$")
# Expected file owner, attached DocType and extension for each generated output.
KINDS = {
    "SLD": ("Project", "Project", "qet"),
    "Customer-Vendor-Agreement": ("Project", "Project", "pdf"),
    "KSEB-Agreement": ("Project", "Project", "pdf"),
    "Check-List": ("Project", "Project", "pdf"),
    "Project-Completion-Report": ("Project", "Project", "pdf"),
    "Project-Report": ("Project Report", "Project", "pdf"),
    "inputs": ("Project Report", "Project Report", "zip"),
}


def is_generated(file, names):
    """`names` maps a DocType to its record names. Identical content shares the first
    file name, so the name prefix may belong to another record of the same DocType."""
    if file.attached_to_field:
        return False
    if file.attached_to_doctype == "KSEB Grid Check":
        match = ANNEXURE.match(file.file_name or "")
        if not match:
            return False
        # Grid Check names end in digits, so the hash suffix is ambiguous; try both readings.
        stem = match["stem"]
        owners = {stem, stem[:-6]} if re.search(r"[0-9a-f]{6}$", stem) else {stem}
        return bool(owners & names["KSEB Grid Check"])
    match = GENERATED.match(file.file_name or "")
    if not match:
        return False
    owner, attached_to, ext = KINDS[match["kind"]]
    # Deleting a Project Report left its PDF on Project, so also accept the report naming series.
    known = match["owner"] in names[owner] or (owner == "Project Report" and REPORT_NAME.match(match["owner"]))
    return file.attached_to_doctype == attached_to and match["ext"] == ext and bool(known)


def generated_files():
    doctypes = ["Project", "Project Report", "KSEB Grid Check"]
    names = {doctype: set(frappe.get_all(doctype, pluck="name")) if frappe.db.exists("DocType", doctype) else set()
             for doctype in ("Project", "Project Report", "KSEB Grid Check")}
    # Files chosen by staff stay, even if their names resemble generated output.
    kept = set()
    for doctype in ("Project Report Attachment", "Project Report Document"):
        if frappe.db.exists("DocType", doctype):
            kept.update(frappe.get_all(doctype, filters={"file": ["is", "set"]}, pluck="file"))
    files = frappe.get_all("File", filters={"attached_to_doctype": ["in", doctypes], "is_folder": 0},
                           fields=["name", "file_name", "file_url", "file_size", "attached_to_doctype",
                                   "attached_to_name", "attached_to_field"])
    return [file for file in files if file.file_url not in kept and is_generated(file, names)]


def execute():
    delete_generated_files()


def delete_generated_files(dry_run=False):
    files = generated_files()
    size = sum(file.file_size or 0 for file in files)
    action = "Would delete" if dry_run else "Deleting"
    print(f"{action} {len(files)} generated files ({size / 1024 / 1024:.1f} MB).")
    failed = []
    for file in files:
        print(f"  {file.attached_to_doctype} {file.attached_to_name}: {file.file_name}")
        if dry_run:
            continue
        try:
            # Frappe removes the stored file once no other File record uses it.
            frappe.delete_doc("File", file.name, ignore_permissions=True)
        except Exception:
            failed.append(file.name)
            frappe.log_error(frappe.get_traceback(), f"Could not delete generated file {file.name}")
    if failed:
        print(f"Could not delete {len(failed)} files; see Error Log.")
    if not dry_run:
        frappe.db.commit()
    return {"files": len(files), "bytes": size, "failed": failed}
