"""Project document and report generation. Output is downloaded, never attached."""

import base64
import hashlib
import json

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from wahni_solar.solar_project.constants import (AGREEMENT_SECTIONS, LEGACY_PANEL_CATEGORIES, OPTIONAL_SECTIONS,
                                                 REPORT_OUTPUTS, REPORT_OUTPUT_SECONDS, SECTIONS)
from wahni_solar.solar_project.documents import merge_pdfs, personalise_qet, select_pdf_pages
from wahni_solar.solar_project.sources import public_context, read_file, resolve_context
from wahni_solar.solar_project.project_documents import DOCUMENT_TYPES, RENDER_CACHE_SECONDS, get_document, render_document


def validate_project(doc, method=None):
    panel_item = doc.get("custom_panel_item")
    if panel_item and frappe.db.get_value("Item", panel_item, "item_group") != "Panel":
        frappe.throw("Select a Panel Item from the Panel item group.")
    seen = set()
    for row in doc.get("custom_report_attachments", []):
        if row.category not in (*SECTIONS, *AGREEMENT_SECTIONS, *LEGACY_PANEL_CATEGORIES):
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


def _result(report):
    result = {key: report.get(key) for key in ("name", "project", "status", "message", "result", "available_until")}
    result["downloads"] = available_outputs(report)
    return result


def _output_key(report_name, output):
    return f"wahni_solar:project_report:{report_name}:{output}"


def available_outputs(report):
    """Generated files are kept briefly in the cache, never attached to a document."""
    until = report.get("available_until")
    if not until or get_datetime(until) <= now_datetime():
        return {}
    return {output: f"/api/method/wahni_solar.solar_project.api.download_project_report"
                    f"?report_name={report.name}&output={output}"
            for output in REPORT_OUTPUTS if frappe.cache.exists(_output_key(report.name, output))}


def clear_outputs(report_name):
    for output in REPORT_OUTPUTS:
        frappe.cache.delete_value(_output_key(report_name, output))


@frappe.whitelist()
def download_project_report(report_name, output="pdf"):
    if output not in REPORT_OUTPUTS:
        frappe.throw("Choose a supported report output.")
    report = frappe.get_doc("Project Report", report_name)
    report.check_permission("read")
    content = frappe.cache.get_value(_output_key(report.name, output), use_local_cache=False)
    if not content:
        frappe.throw("This generated file is no longer available. Generate the report again.")
    frappe.local.response.filename = f"{report.project}-{REPORT_OUTPUTS[output]}"
    frappe.local.response.filecontent = content
    frappe.local.response.type = "pdf" if output == "pdf" else "download"


@frappe.whitelist(methods=["POST"])
def generate_project_document(project, category):
    """Render on demand and return the file to the browser; nothing is stored."""
    if category not in ("SLD", *DOCUMENT_TYPES):
        frappe.throw("Choose SLD or a supported Project document.")
    doc = frappe.get_doc("Project", project)
    doc.check_permission("write")
    source_category = "SLD Template" if category == "SLD" else category
    context = resolve_context(project, categories=(source_category,))
    source = context["sources"][0]
    missing = []
    document = get_document(project, category) if category != "SLD" else None
    if source.get("document_type"):
        content, resolved = render_document(document)
        missing = resolved["missing_fields"]
        context["warnings"].extend(resolved["warnings"])
    elif source.get("url"):
        content, _ = read_file(source["url"])
        if category == "SLD":
            content, missing = personalise_qet(content, context)
        else:
            content = select_pdf_pages(content, source.get("page_from"), source.get("page_to"))
    else:
        frappe.throw(f"{category}: {source.get('reason', 'No source available.')}")
    filename = "SLD.qet" if category == "SLD" else category.replace(" ", "-") + ".pdf"
    return {"filename": f"{doc.name}-{filename}", "content": base64.b64encode(content).decode(),
            "content_type": "application/xml" if category == "SLD" else "application/pdf",
            "category": category, "missing_fields": missing, "warnings": context["warnings"],
            "document": {"doctype": document.doctype, "name": document.name} if document and document.name else None}


def _render_annexure(grid_name, number):
    """Render a fresh annexure without saving it on the Grid Check."""
    from wahni_kseb.annexure.printing import PRINT_FORMATS

    grid = frappe.get_doc("KSEB Grid Check", grid_name)
    grid.check_permission("read")
    grid.check_permission("print")
    for field, label in (("consumer_name", "Consumer Name"), ("consumer_no", "Consumer Number"),
                         ("proposed_solar_capacity", "Proposed Solar Capacity (kW)")):
        if not grid.get(field):
            raise ValueError(f"{label} is missing. Complete the Grid Check before generating Annexure {number}.")
    # Unchanged Grid Checks reuse their PDF. Blank completion dates print the current month.
    format_modified = frappe.db.get_value("Print Format", PRINT_FORMATS[number], "modified")
    key = (f"wahni_solar:rendered:annexure:{grid.name}:{number}:{grid.modified}:{format_modified}:"
           f"{now_datetime():%Y-%m}")
    content = frappe.cache.get_value(key, use_local_cache=False)
    if content is None:
        content = frappe.get_print(grid.doctype, grid.name, print_format=PRINT_FORMATS[number], doc=grid,
                                   as_pdf=True, no_letterhead=1)
        frappe.cache.set_value(key, content, expires_in_sec=RENDER_CACHE_SECONDS)
    return content


def _render_sources(project, context):
    """Return the bytes for each report section, keyed by category. Failures become reasons."""
    contents = {}
    for source in context["sources"]:
        if source["category"] in AGREEMENT_SECTIONS:
            continue
        if not any(source.get(key) for key in ("url", "invoice", "annexure_number", "document_type")):
            continue
        try:
            if source.get("annexure_number"):
                content = _render_annexure(source["name"], source["annexure_number"])
            elif source.get("document_type"):
                doc = get_document(project, source["category"])
                source.update(doctype=doc.doctype, name=doc.name)
                content, resolved = render_document(doc)
                source["missing_fields"] = resolved["missing_fields"]
                context["warnings"].extend(resolved["warnings"])
            elif source.get("invoice"):
                invoice = frappe.get_doc("Sales Invoice", source["invoice"])
                invoice.check_permission("read")
                invoice.check_permission("print")
                print_format = frappe.db.get_single_value("Project Report Settings", "invoice_print_format")
                content = frappe.get_print("Sales Invoice", invoice.name, print_format=print_format or None,
                                           as_pdf=True)
            else:
                content, metadata = read_file(source["url"])
                source.update(metadata)
            source["sha256"] = hashlib.sha256(content).hexdigest()
            contents[source["category"]] = content
        except Exception as exc:
            action = "generate document" if source.get("annexure_number") or source.get("document_type") else "read document"
            source["reason"] = f"Could not {action}: {exc}"
    return contents


def _save_output(report, output, content):
    frappe.cache.set_value(_output_key(report.name, output), content, expires_in_sec=REPORT_OUTPUT_SECONDS)


def build_report(project):
    """Render and merge every section into one PDF. Returns the result and output files."""
    result = {"included": [], "omitted": [], "missing_fields": {}, "warnings": [], "sources": []}
    outputs = {}
    context = resolve_context(project)
    result["warnings"] = context["warnings"]
    contents = _render_sources(project, context)
    sources = {source["category"]: source for source in context["sources"]}
    qet = sources.get("SLD Template", {})
    if "SLD Template" in contents:
        try:
            outputs["qet"], missing = personalise_qet(contents["SLD Template"], context)
            if missing:
                result["missing_fields"]["SLD Drawing"] = missing
        except Exception as exc:
            result["warnings"].append(f"SLD drawing could not be generated: {exc}")
    else:
        result["warnings"].append("SLD drawing: " + qet.get("reason", "No template available."))
    parts = []
    for category in SECTIONS:
        source = sources.get(category, {})
        if category not in contents:
            if category not in OPTIONAL_SECTIONS or source.get("url") or source.get("invoice") or source.get("reason") != "No document available.":
                reason = source.get("reason", "No document available.")
                if category == "Single Line Diagram" and "qet" in outputs:
                    reason = "Drawing generated; PDF export pending."
                result["omitted"].append({"category": category, "reason": reason})
            continue
        try:
            content = select_pdf_pages(contents[category], source.get("page_from"), source.get("page_to"))
            if source.get("missing_fields"):
                result["missing_fields"][category] = source["missing_fields"]
            # Validate this section's form import before adding it to the final set.
            merge_pdfs([(category, content)])
            parts.append((category, content))
            result["sources"].append({key: source.get(key) for key in
                                      ("category", "origin", "doctype", "name", "file", "sha256", "page_from", "page_to", "brand", "panel_watt_peak")})
        except Exception as exc:
            result["omitted"].append({"category": category, "reason": f"Could not include document: {exc}"})
    outputs["pdf"], result["included"] = merge_pdfs(parts)
    result["outputs"] = list(outputs)
    return result, outputs


@frappe.whitelist(methods=["POST"])
def generate_project_report(project):
    """Rendering runs in this request: print formats need the web request's site URL.
    Each Project has one Project Report record, updated by every generation."""
    frappe.get_doc("Project", project).check_permission("write")
    name = frappe.db.get_value("Project Report", {"project": project}, "name")
    if name:
        report = frappe.get_doc("Project Report", name)
        clear_outputs(report.name)
        report.db_set({"requested_by": frappe.session.user, "status": "Running", "progress": 0,
                       "message": None, "result": None, "available_until": None})
    else:
        report = frappe.get_doc({"doctype": "Project Report", "project": project, "requested_by": frappe.session.user,
                                 "status": "Running", "progress": 0}).insert(ignore_permissions=True)
    try:
        result, outputs = build_report(project)
        for output, content in outputs.items():
            _save_output(report, output, content)
        status = "Completed with omissions" if result["omitted"] or result["missing_fields"] or result["warnings"] else "Completed"
        report.db_set({"status": status, "result": json.dumps(result), "progress": 100,
                       "available_until": add_to_date(now_datetime(), seconds=REPORT_OUTPUT_SECONDS),
                       "message": "Report ready. Download it now; generate again later for a fresh copy."})
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "Solar Project Report")
        clear_outputs(report.name)
        report.db_set({"status": "Failed", "message": str(exc), "progress": 100})
    frappe.db.set_value("Project", project, {"custom_latest_project_report": report.name,
                                             "custom_project_report_status": report.status}, update_modified=False)
    return _result(report)
