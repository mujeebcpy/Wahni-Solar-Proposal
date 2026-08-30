# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname

class SolarProposal(Document):
	def autoname(self):
		today = frappe.utils.getdate()
		if today.month >= 4:
			fy_start = today.year % 100
			fy_end = (today.year + 1) % 100
		else:
			fy_start = (today.year - 1) % 100
			fy_end = today.year % 100
		fy = f"{fy_start:02d}-{fy_end:02d}"
		self.name = make_autoname(f"WGT-SQ-{fy}-.###")
