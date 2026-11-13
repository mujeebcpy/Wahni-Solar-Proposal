from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists


class SolarStation(Document):
	def autoname(self):
		base = str(self.station_name or self.external_id).strip()[:120] or "Solar Station"
		self.name = append_number_if_name_exists(self.doctype, base)
