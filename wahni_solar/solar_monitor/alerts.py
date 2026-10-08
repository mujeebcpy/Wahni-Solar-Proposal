"""Deye station alerts, fetched only by explicit user actions."""

import hashlib
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone

from wahni_solar.solar_monitor import service

ALERT = "Solar Alert"
IMPACT = {0: "No Impact", 1: "Production", 2: "Safety", 3: "Production & Safety"}
LEVEL = {0: "Notice", 1: "Warning", 2: "Failure"}
PRIORITY = {"Critical": 3, "Warning": 2, "Notice": 1}
FIELDS = [
	"name",
	"account",
	"station",
	"alert_name",
	"severity",
	"impact",
	"level",
	"alert_code",
	"protocol_name",
	"device_sn",
	"device_type",
	"alert_start",
]


def integer(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def severity(impact, level):
	"""Critical alerts need immediate installer attention: any safety impact or a failure."""
	if impact in (2, 3) or level == 2:
		return "Critical"
	if impact == 1 or level == 1:
		return "Warning"
	return "Notice"


def site_datetime(value):
	"""Provider epoch (seconds, or milliseconds) as a naive datetime in the site time zone."""
	seconds = integer(value)
	if not seconds or seconds < 0:
		return None
	if seconds > 10**11:
		seconds //= 1000
	try:
		instant = datetime.fromtimestamp(seconds, timezone.utc)
	except (OverflowError, OSError, ValueError):
		return None
	return instant.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def station_alerts(account, station_id, start, end):
	result = []
	for page in range(1, 1001):
		data = service.authenticated(
			account,
			"/v1.0/station/alertList",
			{
				"stationId": int(station_id),
				"startTimestamp": start,
				"endTimestamp": end,
				"page": page,
				"size": 200,
			},
		)
		items = data.get("stationAlertItems") or []
		if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
			raise service.ProviderError(_("Provider returned an invalid alert list."))
		result.extend(items)
		total = integer(data.get("total")) or 0
		if not items or len(result) >= total:
			return result
	raise service.ProviderError(_("Provider alert list exceeded the pagination safety limit."))


def alert_key(account, row):
	identity = (
		row.get("alertId") or f"{row.get('deviceSn')}:{row.get('alertCode')}:{row.get('alertStartTime')}"
	)
	return hashlib.sha256((account + "\0" + str(identity)).encode()).hexdigest()


def upsert(account, station, row, seen):
	key = alert_key(account, row)
	name = frappe.db.get_value(ALERT, {"alert_key": key}, "name")
	doc = frappe.get_doc(ALERT, name) if name else frappe.new_doc(ALERT)
	impact, level = integer(row.get("impact")), integer(row.get("level"))
	rank = severity(impact, level)
	doc.update(
		{
			"account": account,
			"station": station,
			"alert_key": key,
			"alert_id": str(row.get("alertId") or ""),
			"alert_name": str(row.get("alertName") or row.get("protocolName") or _("Unnamed alert"))[:140],
			"alert_code": str(row.get("alertCode") or ""),
			"protocol_name": str(row.get("protocolName") or ""),
			"device_sn": str(row.get("deviceSn") or ""),
			"device_type": str(row.get("deviceType") or ""),
			"impact": IMPACT.get(impact, ""),
			"level": LEVEL.get(level, ""),
			"severity": rank,
			"priority": PRIORITY[rank],
			"status": "Open" if integer(row.get("status")) == 1 else "Closed",
			"alert_start": site_datetime(row.get("alertStartTime")),
			"alert_end": site_datetime(row.get("alertEndTime")),
			"last_seen": seen,
		}
	)
	doc.save(ignore_permissions=True)


def check_station(account, station, start, end):
	seen = service.now()
	for row in station_alerts(account, station.external_id, start, end):
		upsert(account, station.name, row, seen)
	# Open alerts inside the checked window that the provider no longer returns are gone.
	table = frappe.qb.DocType(ALERT)
	frappe.qb.update(table).set(table.status, "Closed").where(
		(table.station == station.name)
		& (table.status == "Open")
		& (table.last_seen < seen)
		& (table.alert_start >= site_datetime(start))
	).run()


def enqueue(account):
	with service.lock("solar-monitor-alerts-enqueue:" + account, 30, 5):
		doc = service.account_doc(account)
		elapsed = (
			(service.now() - get_datetime(doc.alert_started_at)).total_seconds()
			if doc.alert_started_at
			else 999999
		)
		if doc.alert_status in ("Queued", "Running") and elapsed < 7200:
			return {"status": doc.alert_status}
		cooldown = service.setting("refresh_cooldown", 120)
		if elapsed < cooldown:
			return {"status": "Cached", "retry_after": int(cooldown - elapsed) + 1}
		frappe.db.set_value(
			service.ACCOUNT,
			account,
			{"alert_status": "Queued", "alert_started_at": service.now(), "alert_error": ""},
		)
		frappe.enqueue(
			"wahni_solar.solar_monitor.alerts.alerts_job",
			queue="long",
			timeout=7200,
			account=account,
			enqueue_after_commit=True,
		)
		return {"status": "Queued"}


def alerts_job(account):
	try:
		with service.lock("solar-monitor-alerts:" + account, 7200, 1):
			_check(account)
	except service.Busy:
		# Another worker is already checking this account; it will update the status.
		pass


def _check(account):
	try:
		service.account_doc(account)
		frappe.db.set_value(service.ACCOUNT, account, "alert_status", "Running")
		frappe.db.commit()
		end = int(time.time())
		start = end - service.setting("alert_lookback_days", 30) * 86400
		stations = frappe.get_all(
			"Solar Station", filters={"account": account, "present": 1}, fields=["name", "external_id"]
		)
		failed = []
		for station in stations:
			try:
				check_station(account, station, start, end)
				# Commit per station so one failing station does not discard the others.
				frappe.db.commit()
			except Exception as exc:
				frappe.db.rollback()
				if not isinstance(exc, service.ProviderError):
					frappe.log_error(title=f"Solar Monitor alert check failed: {station.name}")
				failed.append(station.name)
		if stations and len(failed) == len(stations):
			raise service.ProviderError(_("Alerts could not be fetched for any station."))
		frappe.db.set_value(
			service.ACCOUNT,
			account,
			{
				"alert_status": "Completed",
				"last_alert_sync": service.now(),
				"alert_error": _("Alerts could not be fetched for: {0}").format(", ".join(failed))
				if failed
				else "",
			},
		)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback()
		if not isinstance(exc, service.ProviderError):
			frappe.log_error(title=f"Solar Monitor alert check failed: {account}")
		message = (
			str(exc)
			if isinstance(exc, service.ProviderError)
			else _("Alert check failed. Check configuration and worker availability.")
		)
		frappe.db.set_value(service.ACCOUNT, account, {"alert_status": "Failed", "alert_error": message})
		frappe.db.commit()
