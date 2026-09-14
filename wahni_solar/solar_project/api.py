"""Project report endpoints and background generation."""

import hashlib
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import frappe
from frappe.utils import get_datetime, now_datetime
from frappe.utils.background_jobs import get_job_status
from frappe.utils.file_manager import save_file

from wahni_solar.solar_project.constants import ACTIVE_STATUSES, FORM_SECTIONS, LEGACY_PANEL_CATEGORIES, OPTIONAL_SECTIONS, PANEL_DOCUMENT, SECTIONS
from wahni_solar.solar_project.documents import fill_form, form_values, merge_pdfs, personalise_qet, select_pdf_pages
from wahni_solar.solar_project.sources import public_context, read_file, resolve_context, select_annexure


def validate_project(doc, method=None):
    panel_item = doc.get("custom_panel_item")
    if panel_item and frappe.db.get_value("Item", panel_item, "item_group") != "Panel":
        frappe.throw("Select a Panel Item from the Panel item group.")
    seen = set()
    for row in doc.get("custom_report_attachments", []):
        if row.category not in (*SECTIONS, *LEGACY_PANEL_CATEGORIES):
            frappe.throw("Choose a supported report document category.")
        if row.category in seen:
            frappe.throw(f"Only one Project upload is allowed for {row.category}.")
        seen.add(row.category)
        if row.file:
            # Validate newly attached files, not every existing file on every Project save.
            old = doc.get_doc_before_save()
            previous = {(item.category, item.file) for item in old.get("custom_report_attachments", [])} if old else set()
            if (row.category, row.file) not in previous:
                content, _ = read_file(row.file)
                try:
                    select_pdf_pages(content)
                except Exception as exc:
                    frappe.throw(f"{row.category}: {exc}")


@frappe.whitelist()
def get_project_report_context(project):
    return public_context(resolve_context(project))


def _job_id(report_name):
    return f"solar-project-report-{report_name}"


def _recover_interrupted(report):
    if report.status not in ACTIVE_STATUSES:
        return
    status = get_job_status(_job_id(report.name))
    age = (now_datetime() - get_datetime(report.modified)).total_seconds()
    # Allow the after-commit enqueue callback to complete before treating an absent job as failed.
    if status in ("failed", "stopped", "canceled", "finished") or (status is None and age > 120):
        report.db_set({"status": "Failed", "message": "The background job stopped. Generate the report again."})
        _project_status(report)


def _project_status(report):
    if frappe.db.get_value("Project", report.project, "custom_latest_project_report") == report.name:
        frappe.db.set_value("Project", report.project, "custom_project_report_status", report.status, update_modified=False)


def _result(report):
    return {key: report.get(key) for key in ("name", "project", "status", "progress", "message", "report_pdf",
                                            "sld_qet", "result")}


@frappe.whitelist(methods=["POST"])
def generate_project_report(project):
    doc = frappe.get_doc("Project", project)
    doc.check_permission("write")
    # Serialize requests for this Project through the request transaction's row lock.
    frappe.db.sql("SELECT name FROM `tabProject` WHERE name=%s FOR UPDATE", (project,))
    active = frappe.get_all("Project Report", filters={"project": project, "status": ["in", ACTIVE_STATUSES]},
                            pluck="name", order_by="creation desc")
    for name in active:
        report = frappe.get_doc("Project Report", name)
        _recover_interrupted(report)
        if report.status in ACTIVE_STATUSES:
            return _result(report)

    context = resolve_context(project)
    report = frappe.get_doc({"doctype": "Project Report", "project": project,
                             "requested_by": frappe.session.user, "status": "Queued", "progress": 0,
                             "message": "Waiting for the report worker."}).insert(ignore_permissions=True)
    snapshot = _snapshot(context)
    file = save_file(f"{report.name}-inputs.zip", snapshot, "Project Report", report.name, is_private=1)
    report.db_set("input_snapshot", file.file_url)
    frappe.db.set_value("Project", project, {"custom_latest_project_report": report.name,
                                             "custom_project_report_status": "Queued"}, update_modified=False)
    frappe.enqueue("wahni_solar.solar_project.api.build_report", report_name=report.name, queue="long",
                   timeout=900, job_id=_job_id(report.name), enqueue_after_commit=True)
    return _result(report)


@frappe.whitelist(methods=["POST"])
def get_project_report_status(report_name):
    report = frappe.get_doc("Project Report", report_name)
    report.check_permission("read")
    _recover_interrupted(report)
    return _result(report)


def _ensure_annexure(grid_name, number):
    if number not in (1, 2, 3):
        raise ValueError("Unsupported annexure number.")
    grid = frappe.get_doc("KSEB Grid Check", grid_name)
    grid.check_permission("read")
    # Different Projects may share a Grid Check. Recheck under a row lock before
    # creating an attachment so concurrent report requests reuse the same PDF.
    frappe.db.sql("SELECT name FROM `tabKSEB Grid Check` WHERE name=%s FOR UPDATE", (grid_name,))
    files = frappe.get_all("File", filters={"attached_to_doctype": "KSEB Grid Check",
                           "attached_to_name": grid_name, "is_folder": 0},
                           fields=["file_name", "file_url"], order_by="creation desc, name desc")
    existing = select_annexure(files, number)
    if existing:
        return existing.file_url
    grid.check_permission("write")
    generate = frappe.get_attr(f"wahni_kseb.api.generate_annexure{number}")
    # Reuse the existing validators, templates and attachment behaviour.
    return generate(kseb_grid_check=grid_name)["file_url"]


def _snapshot(context):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for index, source in enumerate(context["sources"]):
            if not source.get("url") and not source.get("invoice") and not source.get("annexure_number"):
                continue
            try:
                if source.get("annexure_number"):
                    source["url"] = _ensure_annexure(source["name"], source["annexure_number"])
                if source.get("invoice"):
                    invoice = frappe.get_doc("Sales Invoice", source["invoice"])
                    invoice.check_permission("read")
                    invoice.check_permission("print")
                    print_format = frappe.db.get_single_value("Project Report Settings", "invoice_print_format")
                    content = frappe.get_print("Sales Invoice", invoice.name, print_format=print_format or None,
                                               as_pdf=True)
                    source["sha256"] = hashlib.sha256(content).hexdigest()
                else:
                    content, metadata = read_file(source["url"])
                    source.update(metadata)
                source["archive_path"] = f"sources/{index:02d}"
                archive.writestr(source["archive_path"], content)
            except Exception as exc:
                action = "generate annexure" if source.get("annexure_number") else "read document"
                source["reason"] = f"Could not {action}: {exc}"
        archive.writestr("context.json", json.dumps(context, default=str))
    return output.getvalue()


def _publish(report, progress, message):
    report.db_set({"progress": progress, "message": message})
    frappe.db.commit()
    frappe.publish_realtime("solar_project_report", _result(report), user=report.requested_by)


def _save_output(report, label, content, field=None):
    file = save_file(f"{report.name}-{label}", content, "Project", report.project, is_private=1)
    if field:
        report.db_set(field, file.file_url)
    return file.file_url


def build_report(report_name):
    report = frappe.get_doc("Project Report", report_name)
    if report.status != "Queued":
        return
    original_user = frappe.session.user
    frappe.set_user(report.requested_by)
    result = {"included": [], "omitted": [], "missing_fields": {}, "warnings": [], "sources": []}
    try:
        if not frappe.db.get_value("User", report.requested_by, "enabled"):
            frappe.throw("The requesting user is disabled.", frappe.PermissionError)
        frappe.get_doc("Project", report.project).check_permission("write")
        report.db_set("status", "Running")
        _project_status(report)
        _publish(report, 5, "Preparing report documents.")
        snapshot, _ = read_file(report.input_snapshot)
        with ZipFile(BytesIO(snapshot)) as archive:
            context = json.loads(archive.read("context.json"))
            for ref in context["permissions"]:
                frappe.get_doc(ref["doctype"], ref["name"]).check_permission("read")
            result["warnings"] = context["warnings"]
            values = form_values(context)
            sources = {source["category"]: source for source in context["sources"]}
            qet = sources.get("SLD Template", {})
            if qet.get("archive_path"):
                try:
                    frappe.get_doc(qet["doctype"], qet["name"]).check_permission("read")
                    content, missing = personalise_qet(archive.read(qet["archive_path"]), context)
                    _save_output(report, "SLD.qet", content, "sld_qet")
                    if missing:
                        result["missing_fields"]["SLD Drawing"] = missing
                except Exception as exc:
                    result["warnings"].append(f"SLD drawing could not be generated: {exc}")
            else:
                result["warnings"].append("SLD drawing: " + qet.get("reason", "No template available."))
            parts = []
            sections = SECTIONS
            # Finish reports queued before the combined panel category was introduced
            # using their original frozen sources and section order.
            if PANEL_DOCUMENT not in sources and any(category in sources for category in LEGACY_PANEL_CATEGORIES):
                sections = tuple(part for category in SECTIONS for part in
                                 (LEGACY_PANEL_CATEGORIES if category == PANEL_DOCUMENT else (category,)))
            for index, category in enumerate(sections):
                source = sources.get(category, {})
                if not source.get("archive_path"):
                    if category not in OPTIONAL_SECTIONS or source.get("url") or source.get("invoice") or source.get("reason") != "No document available.":
                        reason = source.get("reason", "No document available.")
                        if category == "Single Line Diagram" and report.sld_qet:
                            reason = "Drawing generated; PDF export pending."
                        result["omitted"].append({"category": category, "reason": reason})
                    continue
                try:
                    frappe.get_doc(source["doctype"], source["name"]).check_permission("read")
                    content = select_pdf_pages(archive.read(source["archive_path"]), source.get("page_from"), source.get("page_to"))
                    if category in FORM_SECTIONS and source["origin"] == "Library":
                        content, missing = fill_form(content, values[category])
                        if missing:
                            result["missing_fields"][category] = missing
                    # Validate this section's form import before adding it to the final set.
                    merge_pdfs([(category, content)])
                    parts.append((category, content))
                    result["sources"].append({key: source.get(key) for key in
                                              ("category", "origin", "doctype", "name", "file", "sha256", "page_from", "page_to", "brand", "panel_watt_peak")})
                except Exception as exc:
                    result["omitted"].append({"category": category, "reason": f"Could not include document: {exc}"})
                _publish(report, 10 + int(75 * (index + 1) / len(sections)), f"Prepared {category}.")
            content, result["included"] = merge_pdfs(parts)
            _save_output(report, "Project-Report.pdf", content, "report_pdf")
        status = "Completed with omissions" if result["omitted"] or result["missing_fields"] or result["warnings"] else "Completed"
        report.db_set({"status": status, "result": json.dumps(result), "progress": 100,
                       "message": "Report ready. Blank form fields can be completed in a PDF editor."})
    except Exception as exc:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Solar Project Report")
        report.db_set({"status": "Failed", "message": str(exc), "result": json.dumps(result)})
    finally:
        _project_status(report)
        frappe.db.commit()
        frappe.publish_realtime("solar_project_report", _result(report), user=report.requested_by)
        frappe.set_user(original_user)
