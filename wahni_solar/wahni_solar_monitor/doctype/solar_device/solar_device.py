import frappe
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists


class SolarDevice(Document):
	def autoname(self):
		station_name = frappe.db.get_value("Solar Station", self.station, "station_name") or self.station
		base = f"{self.device_type or 'Device'} - {station_name}".strip()[:120]
		self.name = append_number_if_name_exists(self.doctype, base)
