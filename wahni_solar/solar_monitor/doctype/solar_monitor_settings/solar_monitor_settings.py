import frappe
from frappe import _
from frappe.model.document import Document


class SolarMonitorSettings(Document):
	def validate(self):
		for key in (
			"refresh_cooldown",
			"token_renewal_margin",
			"requests_per_minute",
			"production_refresh_cooldown",
		):
			if not self.get(key) or self.get(key) < 1:
				frappe.throw(_("Solar Monitor settings must be positive numbers."))
