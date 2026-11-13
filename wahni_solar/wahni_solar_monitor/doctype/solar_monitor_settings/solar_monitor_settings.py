import frappe
from frappe import _
from frappe.model.document import Document


class SolarMonitorSettings(Document):
	def validate(self):
		# Settings saved before these fields existed have no value yet.
		self.alert_lookback_days = self.alert_lookback_days or 30
		self.enphase_requests_per_minute = self.enphase_requests_per_minute or 300
		for key in (
			"refresh_cooldown",
			"token_renewal_margin",
			"requests_per_minute",
			"enphase_requests_per_minute",
			"production_refresh_cooldown",
			"alert_lookback_days",
		):
			if not self.get(key) or self.get(key) < 1:
				frappe.throw(_("Solar Monitor settings must be positive numbers."))
		if self.alert_lookback_days > 180:
			frappe.throw(_("Deye allows at most 180 days of alert history per request."))
