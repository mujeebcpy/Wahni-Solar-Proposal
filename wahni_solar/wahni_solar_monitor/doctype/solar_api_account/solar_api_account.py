import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import set_encrypted_password


class SolarAPIAccount(Document):
	def validate(self):
		if self.enabled and self.provider not in ("Deye", "Enphase"):
			frappe.throw(
				_(
					"Only Deye and Enphase can be enabled. Disable this account to save future provider credentials."
				)
			)
		if self.enabled and self.provider == "Deye":
			for key in ("app_id", "email", "company_id"):
				if not self.get(key):
					frappe.throw(_("Deye requires App ID, email and company ID."))
			if not str(self.company_id).isdigit():
				frappe.throw(_("Deye Company ID must be numeric."))
			for key in ("app_secret", "password"):
				if not self.get_password(key, raise_exception=False):
					frappe.throw(_("Deye requires an app secret and normal password."))
		if self.enabled and self.provider == "Enphase":
			if not self.client_id:
				frappe.throw(_("Enphase requires the Client ID, Client Secret and API Key."))
			for key in ("client_secret", "api_key"):
				if not self.get_password(key, raise_exception=False):
					frappe.throw(_("Enphase requires the Client ID, Client Secret and API Key."))
			if self.redirect_uri and not self.redirect_uri.strip().startswith("https://"):
				frappe.throw(_("Enphase Redirect URI must start with https://."))
		old = self.get_doc_before_save()
		if old:
			changed = any(
				self.get(k) != old.get(k)
				for k in (
					"provider",
					"app_id",
					"email",
					"region",
					"company_id",
					"client_id",
					"enphase_username",
				)
			)
			changed = changed or any(
				self.get(k) and not self.is_dummy_password(self.get(k))
				for k in ("password", "app_secret", "client_secret", "enphase_password")
			)
			if changed:
				self.expires_at = None
				self.connection_status = "Not connected"
				for key in ("access_token", "refresh_token"):
					set_encrypted_password(self.doctype, self.name, "", key)
			if any(self.get(k) != old.get(k) for k in ("provider", "email", "region", "company_id")):
				self.company_name = None
				self.company_details_fetched_at = None
				self.company_lookup_attempted = 0
				self.company_lookup_error = None
