import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from wahni_solar.solar_monitor import alerts, service

MANAGER_ROLES = ["System Manager"]
VIEWER_ROLES = ["System Manager", "Solar Monitor Viewer"]


@frappe.whitelist(methods=["POST"])
def test_connection(account: str):
	frappe.only_for(MANAGER_ROLES)
	service.account_doc(account)
	with service.lock(
		"solar-monitor-test:" + account, 300, 1, _("A connection test is already running for this account.")
	):
		key = "solar-monitor-test-time:" + account
		if frappe.cache().get_value(key):
			frappe.throw(_("Wait 30 seconds before testing again."))
		frappe.cache().set_value(key, 1, expires_in_sec=30)
		try:
			service.ensure_token(account)
			service.company_details(account)
			frappe.db.set_value(
				service.ACCOUNT, account, {"connection_status": "Connected", "authentication_error": ""}
			)
			return {
				"status": "Connected",
				"expires_at": frappe.db.get_value(service.ACCOUNT, account, "expires_at"),
			}
		except service.ProviderError as exc:
			if isinstance(exc, service.Busy):
				raise
			frappe.db.set_value(
				service.ACCOUNT, account, {"connection_status": "Error", "authentication_error": str(exc)}
			)
			return {"status": "Error", "error": str(exc)}


@frappe.whitelist(methods=["POST"])
def fetch_company_details(account: str):
	frappe.only_for(MANAGER_ROLES)
	key = "solar-monitor-company-click:" + account
	with service.lock(key + ":lock", 300, 1, _("Company details are already being fetched.")):
		if frappe.cache().get_value(key):
			frappe.throw(_("Wait 30 seconds before updating company details again."))
		frappe.cache().set_value(key, 1, expires_in_sec=30)
		service.company_details(account, manual=True)
	return frappe.db.get_value(
		service.ACCOUNT, account, ["company_name", "company_lookup_error"], as_dict=True
	)


@frappe.whitelist(methods=["POST"])
def sync_inventory(account: str):
	frappe.only_for(MANAGER_ROLES)
	with service.lock(
		"solar-monitor-enqueue:" + account,
		30,
		5,
		_("Inventory fetch is already being queued for this account."),
	):
		doc = service.account_doc(account)
		elapsed = (
			(service.now() - get_datetime(doc.sync_started_at)).total_seconds()
			if doc.sync_started_at
			else 999999
		)
		if doc.sync_status in ("Queued", "Running") and elapsed < 7200:
			return {"status": doc.sync_status}
		if elapsed < service.setting("refresh_cooldown", 120):
			frappe.throw(_("Inventory was requested recently. Wait for the refresh cooldown."))
		frappe.db.set_value(
			service.ACCOUNT,
			account,
			{"sync_status": "Queued", "sync_started_at": service.now(), "sync_error": ""},
		)
		frappe.enqueue(
			"wahni_solar.solar_monitor.service.sync_job",
			queue="long",
			timeout=7200,
			account=account,
			enqueue_after_commit=True,
		)
	return {"status": "Queued"}


@frappe.whitelist(methods=["GET"])
def get_overview(
	provider: str = "Deye",
	account: str | None = None,
	station: str | None = None,
	start: int = 0,
	search: str | None = None,
):
	frappe.only_for(VIEWER_ROLES)
	from wahni_solar.solar_monitor import production

	if provider not in ("Deye", "Enphase", "Solarman"):
		frappe.throw(_("Unknown provider."))
	# Viewers have no read permission on Solar API Account; only non-secret display fields are returned.
	accounts = frappe.get_all(
		service.ACCOUNT,
		filters={"provider": provider},
		fields=[
			"name",
			"account_label",
			"company_name",
			"connection_status",
			"last_successful_sync",
			"sync_status",
			"sync_error",
			"company_lookup_error",
			"alert_status",
			"last_alert_sync",
			"alert_error",
		],
	)
	allowed = {x.name for x in accounts}
	if account and account not in allowed:
		frappe.throw(_("Account does not belong to this provider."))
	filters = {"account": account} if account else {"account": ["in", list(allowed)]}
	rows = frappe.get_list(
		"Solar Station",
		filters=dict(filters, present=1),
		fields=production.FIELDS,
		order_by="station_name",
		page_length=0,
	)
	rows = [production.display(row) for row in rows]
	summary = production.totals(rows)
	station_names = {r.name: r.station_name or r.name for r in rows}
	open_alerts = frappe.get_list(
		alerts.ALERT,
		filters=dict(filters, status="Open"),
		fields=alerts.FIELDS,
		order_by="priority desc, alert_start desc",
		page_length=100,
	)
	for row in open_alerts:
		row.station_name = station_names.get(row.station, row.station)
	alert_counts = {
		row.severity: row.count
		for row in frappe.get_list(
			alerts.ALERT,
			filters=dict(filters, status="Open"),
			fields=["severity", "count(name) as count"],
			group_by="severity",
		)
	}
	if station:
		rows = [r for r in rows if r.name == station]
	if search:
		rows = [r for r in rows if search.lower() in (r.station_name or r.name).lower()]
	offset = max(0, cint(start))
	return {
		"accounts": accounts,
		"alerts": open_alerts,
		"alert_counts": alert_counts,
		"stations": rows[offset : offset + 100],
		"filtered_count": len(rows),
		"summary": summary,
		"station_count": summary["station_count"],
		"device_count": frappe.db.count("Solar Device", dict(filters, present=1)),
		"can_manage": "System Manager" in frappe.get_roles(),
		"busy": any(r.production_status in ("Queued", "Running") for r in rows),
	}


@frappe.whitelist(methods=["GET"])
def get_station(station: str):
	frappe.only_for(VIEWER_ROLES)
	from wahni_solar.solar_monitor import production

	doc = frappe.get_doc("Solar Station", station)
	doc.check_permission("read")
	row = frappe._dict({key: doc.get(key) for key in production.FIELDS})
	return {
		"station": production.display(row),
		"devices": frappe.get_list(
			"Solar Device",
			filters={"station": station, "present": 1},
			fields=["name", "external_id", "device_type"],
			page_length=0,
		),
		"alerts": frappe.get_list(
			alerts.ALERT,
			filters={"station": station, "status": "Open"},
			fields=alerts.FIELDS,
			order_by="priority desc, alert_start desc",
			page_length=0,
		),
		"can_manage": "System Manager" in frappe.get_roles(),
	}


@frappe.whitelist(methods=["POST"])
def refresh_station(station: str):
	frappe.only_for(MANAGER_ROLES)
	from wahni_solar.solar_monitor import production

	return production.enqueue(station)


@frappe.whitelist(methods=["POST"])
def refresh_production(account: str | None = None):
	frappe.only_for(MANAGER_ROLES)
	from wahni_solar.solar_monitor import production

	accounts = frappe.get_all(service.ACCOUNT, filters={"provider": "Deye", "enabled": 1}, pluck="name")
	if account and account not in accounts:
		frappe.throw(_("Select an enabled Deye account."))
	rows = frappe.get_list(
		"Solar Station",
		filters={"account": ["in", [account] if account else accounts], "present": 1},
		pluck="name",
		page_length=0,
	)
	result = {"Queued": 0, "Running": 0, "Cached": 0}
	for station in rows:
		try:
			state = production.enqueue(station)["status"]
		except service.Busy:
			# Another request is queueing this station right now.
			state = "Running"
		result[state] += 1
	return result


@frappe.whitelist(methods=["POST"])
def check_alerts(account: str | None = None):
	"""Queue an alert check covering every present station of one or all enabled Deye accounts."""
	frappe.only_for(MANAGER_ROLES)
	accounts = frappe.get_all(service.ACCOUNT, filters={"provider": "Deye", "enabled": 1}, pluck="name")
	if account and account not in accounts:
		frappe.throw(_("Select an enabled Deye account."))
	result = {"Queued": 0, "Running": 0, "Cached": 0}
	for name in [account] if account else accounts:
		try:
			state = alerts.enqueue(name)["status"]
		except service.Busy:
			state = "Running"
		result[state] += 1
	return result
