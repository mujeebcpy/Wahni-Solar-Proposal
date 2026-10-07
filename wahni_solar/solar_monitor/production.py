"""Cached production snapshots, fetched only by explicit user actions."""

import math
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.utils import get_datetime

from wahni_solar.solar_monitor import service

FIELDS = [
	"name",
	"account",
	"station_name",
	"external_id",
	"timezone",
	"location",
	"capacity_kw",
	"connection_status",
	"present",
	"production_power_kw",
	"daily_production_kwh",
	"monthly_production_kwh",
	"total_production_kwh",
	"has_power",
	"has_daily",
	"has_monthly",
	"has_total",
	"production_date",
	"source_updated_at",
	"last_production_fetch",
	"production_status",
	"production_error",
]


def local_date(station):
	try:
		tz = ZoneInfo(station.timezone or "Asia/Kolkata")
	except (ZoneInfoNotFoundError, ValueError):
		raise service.ProviderError(
			_("Station timezone is invalid. Synchronize inventory to update it.")
		) from None
	return service.utcnow().replace(tzinfo=timezone.utc).astimezone(tz).date()


def number(value):
	if value is None or isinstance(value, bool):
		return None
	try:
		result = float(value)
		return result if math.isfinite(result) else None
	except (ValueError, TypeError):
		return None


def energy(rows):
	values = [number(row.get("generationValue")) for row in rows]
	return sum(values) if values and all(x is not None for x in values) else None


def history(account, body):
	# History uses bounded date ranges, not the inventory page/size body fields.
	data = service.authenticated(account, "/v1.0/station/history", body)
	rows = data.get("stationDataItems")
	if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
		raise service.ProviderError(_("Provider returned invalid production history."))
	try:
		total = int(data["total"])
	except (KeyError, ValueError, TypeError):
		raise service.ProviderError(_("Provider history response is missing its total count.")) from None
	if total != len(rows):
		raise service.ProviderError(
			_("Provider returned incomplete production history. Saved readings were preserved.")
		)
	return rows


def snapshot(station):
	today = local_date(station)
	sid = int(station.external_id)
	latest = service.authenticated(station.account, "/v1.0/station/latest", {"stationId": sid})
	days = history(
		station.account,
		{
			"stationId": sid,
			"granularity": 2,
			"startAt": str(today.replace(day=1)),
			"endAt": str(today + timedelta(days=1)),
		},
	)
	# Deye sample specifies endAt is excluded. Annual rows provide lifetime energy
	# without polling devices or deriving energy from instantaneous power.
	start_year = get_datetime(station.operating_since).year if station.operating_since else 2000
	years = history(
		station.account,
		{"stationId": sid, "granularity": 4, "startAt": str(start_year), "endAt": str(today.year + 1)},
	)
	daily_rows = [
		row
		for row in days
		if str(row.get("year")) == str(today.year)
		and str(row.get("month")) == str(today.month)
		and str(row.get("day")) == str(today.day)
	]
	month_rows = [
		row
		for row in days
		if str(row.get("year")) == str(today.year) and str(row.get("month")) == str(today.month)
	]
	values = {
		"production_power_kw": number(latest.get("generationPower")),
		"daily_production_kwh": energy(daily_rows),
		"monthly_production_kwh": energy(month_rows),
		"total_production_kwh": energy(years),
	}
	# Deye power is in W; energy values are in kWh.
	if values["production_power_kw"] is not None:
		values["production_power_kw"] /= 1000
	for flag, field in [
		("has_power", "production_power_kw"),
		("has_daily", "daily_production_kwh"),
		("has_monthly", "monthly_production_kwh"),
		("has_total", "total_production_kwh"),
	]:
		values[flag] = int(values[field] is not None)
	values.update(
		production_date=today,
		source_updated_at=str(latest.get("lastUpdateTime") or ""),
		last_production_fetch=service.now(),
		production_status="Completed",
		production_error="",
	)
	return values


def display(row):
	try:
		today = local_date(row)
	except service.ProviderError as exc:
		row.production_error = str(exc)
		row.daily_production_kwh = None
		row.monthly_production_kwh = None
		row.production_power_kw = None
		row.stale = True
		return row
	saved_date = str(row.production_date or "")
	for field, flag in [
		("production_power_kw", "has_power"),
		("daily_production_kwh", "has_daily"),
		("monthly_production_kwh", "has_monthly"),
		("total_production_kwh", "has_total"),
	]:
		if not row.get(flag):
			row[field] = None
	if saved_date != str(today):
		row.daily_production_kwh = None
		row.production_power_kw = None
	if saved_date[:7] != str(today)[:7]:
		row.monthly_production_kwh = None
	row.stale = (
		not row.last_production_fetch
		or (service.now() - get_datetime(row.last_production_fetch)).total_seconds() > 600
	)
	source_time = number(row.get("source_updated_at"))
	if source_time is not None:
		row.stale = row.stale or service.utcnow().replace(tzinfo=timezone.utc).timestamp() - source_time > 600
	return row


def totals(rows):
	result = {
		"station_count": len(rows),
		"online_count": sum(r.connection_status == "NORMAL" for r in rows),
		"capacity_kw": sum(number(r.capacity_kw) or 0 for r in rows),
	}
	for field in [
		"production_power_kw",
		"daily_production_kwh",
		"monthly_production_kwh",
		"total_production_kwh",
	]:
		values = [r.get(field) for r in rows if r.get(field) is not None]
		result[field] = sum(values) if values else None
		result[field + "_coverage"] = len(values)
	result["stale_count"] = sum(bool(r.stale) for r in rows)
	return result


def enqueue(station):
	with service.lock("solar-monitor-production-enqueue:" + station, 30, 5):
		doc = frappe.get_doc("Solar Station", station)
		service.account_doc(doc.account)
		if not doc.present:
			frappe.throw(_("This station is no longer in the current inventory."))
		elapsed = (
			(service.now() - get_datetime(doc.production_requested_at)).total_seconds()
			if doc.production_requested_at
			else 999999
		)
		if doc.production_status in ("Queued", "Running") and elapsed < 600:
			return {"status": doc.production_status}
		if elapsed < service.setting("production_refresh_cooldown", 300):
			return {
				"status": "Cached",
				"retry_after": int(service.setting("production_refresh_cooldown", 300) - elapsed) + 1,
			}
		frappe.db.set_value(
			"Solar Station",
			station,
			{
				"production_status": "Queued",
				"production_requested_at": service.now(),
				"production_error": "",
			},
		)
		frappe.enqueue(
			"wahni_solar.solar_monitor.production.refresh_job",
			station=station,
			queue="long",
			timeout=600,
			enqueue_after_commit=True,
		)
		return {"status": "Queued"}


def refresh_job(station):
	try:
		with service.lock("solar-monitor-production:" + station, 600, 1):
			_refresh(station)
	except service.Busy:
		# Another worker is already refreshing this station.
		pass


def _refresh(station):
	if not frappe.db.exists("Solar Station", station):
		return
	try:
		doc = frappe.get_doc("Solar Station", station)
		service.account_doc(doc.account)
		if not doc.present:
			raise service.ProviderError(_("Station is no longer in the inventory."))
		frappe.db.set_value("Solar Station", station, "production_status", "Running")
		frappe.db.commit()
		values = snapshot(doc)
		frappe.db.set_value("Solar Station", station, values)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback()
		if not isinstance(exc, service.ProviderError):
			frappe.log_error(title=f"Solar Monitor production update failed: {station}")
		error = (
			str(exc)
			if isinstance(exc, service.ProviderError)
			else _("Production update failed. Check provider access and station configuration.")
		)
		frappe.db.set_value(
			"Solar Station", station, {"production_status": "Failed", "production_error": error}
		)
		frappe.db.commit()
