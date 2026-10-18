"""Server-only Enphase Monitoring API v4 connector. Never expose provider response bodies in errors.

OAuth 2.0: an installer or system owner approves the application in the browser (authorization code),
or Partner-plan applications use the installer's Enlighten login (password grant). Access tokens last
one day and are renewed with the refresh token (one month); every API call also sends the API key.
"""

import base64
import hashlib
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password

from wahni_solar.solar_monitor import alerts, production, service

API = "https://api.enphaseenergy.com/api/v4"
OAUTH = "https://api.enphaseenergy.com/oauth"
DEFAULT_REDIRECT_URI = OAUTH + "/redirect_uri"
# Enlighten labels for the API's system status values.
STATUS = {
	"normal": "System Normal",
	"deactivated": "System Deactivated",
	"comm": "Envoy Not Reporting",
	"micro": "Microinverters Not Reporting",
	"power": "System Production Issue",
	"meter": "Meter Not Reporting",
	"meter_issue": "Meter Issue",
	"battery": "AC Batteries Not Reporting",
	"storage_idle": "Storage Inactive",
	"encharge": "Encharge Not Reporting",
	"encharge_issue": "Encharge Issue",
	"enpower": "Enpower Not Reporting",
	"enpower_issue": "Enpower Issue",
	"retired": "Retired",
	"not_monitored": "Not Monitored",
	"unused": "Unused",
	"disabled": "Not Enabled",
	"no_data": "No Data",
	"rma": "RMA",
	"unknown": "Updating Data",
	"nsr": "Q Relay Not Reporting",
	"data_upload": "Data upload in progress",
	"on_grid": "On Grid",
	"off_grid": "Off Grid",
	"grid_unknown": "Grid Status Unknown",
	"iq_collar": "Meter Collar Not Reporting",
}
DEVICE_TYPES = {
	"micros": "Microinverter",
	"meters": "Meter",
	"gateways": "Gateway",
	"q_relays": "IQ Relay",
	"acbs": "AC Battery",
	"encharges": "IQ Battery",
	"enpowers": "IQ System Controller",
	"ev_chargers": "EV Charger",
	"heat_pump": "Heat Pump",
	"iq_collars": "IQ Meter Collar",
	"iq_air": "IQ Air",
	"generators": "Generator",
}
# Alarm severity: FATAL = 1, ERROR = 2, WARNING = 3, INFO = 4, DEBUG = 5, NONE = 6.
SEVERITY = {1: "Critical", 2: "Critical", 3: "Warning"}
LEVEL = {1: "Failure", 2: "Failure", 3: "Warning"}


def status_label(value):
	return STATUS.get(str(value or "").lower(), str(value or "")) or None


# OAuth


def redirect_uri(doc):
	return (doc.redirect_uri or "").strip() or DEFAULT_REDIRECT_URI


def authorize_url(doc, state):
	query = {
		"response_type": "code",
		"client_id": doc.client_id,
		"redirect_uri": redirect_uri(doc),
		"state": state,
	}
	return OAUTH + "/authorize?" + urlencode(query)


def token_request(doc, params=None, data=None, refresh="", rejected=None):
	"""POST to the token endpoint with HTTP Basic client credentials; returns a normalized token dict.

	`rejected` replaces the generic message when the grant itself is refused (HTTP 400 invalid_grant).
	"""
	credentials = f"{doc.client_id}:{service.secret(doc, 'client_secret')}".encode()
	try:
		response = service.send(
			doc,
			"POST",
			OAUTH + "/token",
			headers={"Authorization": "Basic " + base64.b64encode(credentials).decode()},
			params=params,
			data=data,
		)
	except service.ProviderHTTPError as exc:
		if exc.status == 401:
			raise service.ProviderHTTPError(
				_("Enphase rejected the Client ID or Client Secret."), exc.status
			) from None
		if exc.status == 400 and rejected:
			raise service.ProviderHTTPError(rejected, exc.status) from None
		raise
	body = service.json_body(response)
	return {
		"access_token": body.get("access_token"),
		# Keep the current refresh token when a renewal does not rotate it.
		"refresh_token": body.get("refresh_token") or refresh,
		"expires_in": body.get("expires_in"),
		"token_type": body.get("token_type"),
		"scope": body.get("scope"),
		"uid": body.get("enl_uid") or "",
	}


def renew_token(doc):
	refresh = get_decrypted_password(service.ACCOUNT, doc.name, "refresh_token", raise_exception=False)
	if refresh:
		try:
			return token_request(
				doc, params={"grant_type": "refresh_token", "refresh_token": refresh}, refresh=refresh
			)
		except service.ProviderHTTPError as exc:
			# 400/401 mean the refresh token expired or was revoked; anything else is a real failure.
			if exc.status not in (400, 401):
				raise
	password = get_decrypted_password(service.ACCOUNT, doc.name, "enphase_password", raise_exception=False)
	if doc.enphase_username and password:
		return token_request(
			doc,
			data={"grant_type": "password", "username": doc.enphase_username, "password": password},
			rejected=_(
				"Enphase rejected the Enlighten username or password. Use the installer's Enlighten login, or clear both fields and use Authorize with Enphase."
			),
		)
	raise service.ProviderError(
		_("Enphase authorization is missing or expired. Use Authorize with Enphase on the API account.")
	)


def authorization_code(value):
	"""Accept the bare code or the whole redirect URL pasted from the browser address bar."""
	value = (value or "").strip()
	if "code=" in value:
		value = (parse_qs(urlparse(value).query or value.split("?", 1)[-1]).get("code") or [""])[0]
	if not value or len(value) > 512:
		raise service.ProviderError(_("Enter the authorization code returned by Enphase."))
	return value


def exchange_code(name, code):
	code = authorization_code(code)
	with service.token_lock(name):
		doc = service.account_doc(name)
		started = service.now()
		data = token_request(
			doc,
			params={"grant_type": "authorization_code", "redirect_uri": redirect_uri(doc), "code": code},
			rejected=_(
				"Enphase rejected the authorization code. Codes work once and expire quickly; authorize again."
			),
		)
		return service.save_token(name, data, started)


# Monitoring API


def get(doc, path, params, token):
	response = service.send(
		doc,
		"GET",
		API + path,
		token=token,
		headers={"key": service.secret(doc, "api_key"), "Accept": "application/json"},
		params=params or None,
	)
	return service.json_body(response)


def location(address):
	if not isinstance(address, dict):
		return None
	parts = [address.get(k) for k in ("city", "state", "country", "postal_code")]
	return ", ".join(str(x) for x in parts if x) or None


def inventory(account):
	"""Returns ([(system_id, values)], [(system_id, serial, device_type)])."""
	stations, devices = [], []
	for row in service.pages(account, "/systems", "systems"):
		system_id = row.get("system_id")
		if not system_id:
			raise service.ProviderError(_("Provider returned a system without an ID."))
		# Capacity is deprecated in the systems list; production updates fill it from the summary.
		stations.append(
			(
				system_id,
				{
					"station_name": row.get("name"),
					"timezone": row.get("timezone"),
					"connection_status": status_label(row.get("status")),
					"location": location(row.get("address")),
					"operating_since": service.operating_date(row.get("operational_at")),
				},
			)
		)
		groups = service.authenticated(account, f"/systems/{int(system_id)}/devices", {}).get("devices") or {}
		if not isinstance(groups, dict) or any(not isinstance(x, list) for x in groups.values()):
			raise service.ProviderError(_("Provider returned an invalid device list."))
		for kind, items in groups.items():
			for item in items:
				# Some device kinds (e.g. third-party heat pumps) have no serial and cannot be tracked.
				if not isinstance(item, dict) or not item.get("serial_number") or item.get("active") is False:
					continue
				label = DEVICE_TYPES.get(kind, kind.replace("_", " ").title())
				devices.append((system_id, str(item["serial_number"]), label))
	return stations, devices


def watts(value):
	result = production.number(value)
	return result if result is not None and result >= 0 else None


def provider_date(value):
	try:
		return datetime.strptime(str(value), "%Y-%m-%d").date()
	except (TypeError, ValueError):
		return None


def snapshot(station):
	"""Two calls: the summary (power, today, lifetime) and this month's daily series before today."""
	sid = int(station.external_id)
	summary = service.authenticated(station.account, f"/systems/{sid}/summary", {})
	day = provider_date(summary.get("summary_date")) or production.local_date(station)
	today = watts(summary.get("energy_today"))
	before_today = watts(summary.get("energy_lifetime"))
	month = today
	if day.day > 1 and today is not None:
		series = service.authenticated(
			station.account,
			f"/systems/{sid}/energy_lifetime",
			{"start_date": str(day.replace(day=1)), "end_date": str(day - timedelta(days=1))},
		).get("production")
		if not isinstance(series, list):
			raise service.ProviderError(_("Provider returned invalid production history."))
		days = [watts(x) for x in series]
		month = None if any(x is None for x in days) else sum(days) + today
	power = watts(summary.get("current_power"))
	# Enphase power is in W and energy in Wh.
	values = {
		"production_power_kw": None if power is None else power / 1000,
		"daily_production_kwh": None if today is None else today / 1000,
		"monthly_production_kwh": None if month is None else month / 1000,
		"total_production_kwh": None
		if today is None or before_today is None
		else (before_today + today) / 1000,
	}
	size = watts(summary.get("size_w"))
	if size:
		values["capacity_kw"] = size / 1000
	if summary.get("status"):
		values["connection_status"] = status_label(summary["status"])
	return production.completed(values, day, summary.get("last_report_at"))


# Alerts


def event_types(account):
	"""Event names by type ID, cached for a day to save API quota. Failures fall back to IDs."""
	key = "solar-monitor-enphase-event-types:" + hashlib.sha256(account.encode()).hexdigest()
	cache = frappe.cache()
	names = cache.get_value(key)
	if names is not None:
		return names
	try:
		rows = service.authenticated(account, "/systems/event_types", {}).get("event_types") or []
		names = {
			str(row.get("event_type_id")): {"name": row.get("event_name"), "key": row.get("event_type_key")}
			for row in rows
			if isinstance(row, dict)
		}
	except service.ProviderError:
		names = {}
	cache.set_value(key, names, expires_in_sec=86400 if names else 3600)
	return names


def serials(events):
	if isinstance(events, dict):
		events = [x for group in events.values() if isinstance(group, list) for x in group]
	return [str(x["serial_number"]) for x in events or [] if isinstance(x, dict) and x.get("serial_number")]


def alarm_values(row, names):
	level = alerts.integer(row.get("severity"))
	rank = SEVERITY.get(level, "Notice")
	event = names.get(str(row.get("event_type_id"))) or {}
	devices = serials(row.get("events"))
	device = devices[0] + (f" (+{len(devices) - 1})" if len(devices) > 1 else "") if devices else ""
	return {
		"alert_id": str(row.get("id") or ""),
		"alert_name": str(event.get("name") or _("Enphase event {0}").format(row.get("event_type_id")))[:140],
		"alert_code": str(row.get("event_type_id") or ""),
		"protocol_name": str(event.get("key") or ""),
		"device_sn": device[:140],
		"device_type": "",
		"impact": "",
		"level": LEVEL.get(level, "Notice"),
		"severity": rank,
		"priority": alerts.PRIORITY[rank],
		"status": "Closed" if row.get("cleared") is True else "Open",
		"alert_start": alerts.site_datetime(row.get("alarm_start_time")),
		"alert_end": alerts.site_datetime(row.get("alarm_end_time")),
	}


def check_station(account, station, start=None, end=None):
	"""Open alarms are the complete current set, so every other open alert of the station is closed."""
	seen = service.now()
	rows = (
		service.authenticated(account, f"/systems/{int(station.external_id)}/open_alarms", {}).get("alarms")
		or []
	)
	if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
		raise service.ProviderError(_("Provider returned an invalid alert list."))
	names = event_types(account) if rows else {}
	for row in rows:
		identity = row.get("id") or f"{row.get('event_type_id')}:{row.get('alarm_start_time')}"
		key = alerts.hashed(account, "enphase-alarm:" + str(identity))
		alerts.save(account, station.name, key, alarm_values(row, names), seen)
	alerts.close_missing(station.name, seen)
