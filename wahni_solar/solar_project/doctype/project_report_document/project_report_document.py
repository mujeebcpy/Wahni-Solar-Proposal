import frappe
from frappe.model.document import Document
from frappe.utils import cint

from wahni_solar.solar_project.constants import LEGACY_PANEL_CATEGORIES, LIBRARY_CATEGORIES, PANEL_DOCUMENT
from wahni_solar.solar_project.documents import parse_qet, select_pdf_pages


class ProjectReportDocument(Document):
    def validate(self):
        from wahni_solar.solar_project.sources import read_file

        self.brand = (self.brand or "").strip()
        self.model = (self.model or "").strip()
        if self.category not in (*LIBRARY_CATEGORIES, *LEGACY_PANEL_CATEGORIES):
            frappe.throw("Choose a supported report document category.")
        if self.category in LEGACY_PANEL_CATEGORIES:
            previous = self.get_doc_before_save()
            if not previous or previous.category != self.category:
                frappe.throw("For panel uploads, choose Panel Datasheet and BIS and attach one combined PDF with its brand and Wp.")
        if self.category == PANEL_DOCUMENT:
            self.model = ""
            if self.enabled and (not self.brand or cint(self.panel_watt_peak) <= 0):
                frappe.throw("Enabled combined panel documents require an Equipment Brand and a positive Panel Watt Peak (Wp).")
        if not self.file:
            return
        content, _ = read_file(self.file)
        try:
            if self.category == "SLD Template":
                parse_qet(content)
            else:
                select_pdf_pages(content, self.page_from, self.page_to)
        except Exception as exc:
            frappe.throw(f"Invalid report document: {exc}")
