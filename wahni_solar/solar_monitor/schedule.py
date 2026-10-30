"""Daily automatic refresh: production for every station, then a triaged alert check.

Runs after sunset so today's energy is final, unless Auto Daily Refresh is off in Solar Monitor
Settings. Sundays sweep every Enphase station's alarms. Accounts
that service.account_doc refuses (disabled or unsupported) or that have
used their Enphase monthly budget are skipped; manual updates use the same cooldowns and budget.
"""

import frappe

from wahni_solar.solar_monitor import alerts, production, service

SUNDAY = 6


def daily_refresh():
	if not frappe.db.get_single_value("Solar Monitor Settings", "auto_daily_refresh"):
		return
	full_sweep = service.now().weekday() == SUNDAY
	for account in frappe.get_all(
		service.ACCOUNT, filters={"enabled": 1, "provider": ["in", service.PROVIDERS]}, pluck="name"
	):
		try:
			doc = service.account_doc(account)
			service.check_budget(doc)
		except service.ProviderError:
			frappe.clear_last_message()
			continue
		for station in frappe.get_all(
			"Solar Station", filters={"account": account, "present": 1}, pluck="name"
		):
			try:
				production.enqueue(station)
			except Exception:
				frappe.log_error(title=f"Solar Monitor scheduled production failed: {station}")
		try:
			alerts.enqueue(account, full=full_sweep)
		except Exception:
			frappe.log_error(title=f"Solar Monitor scheduled alert check failed: {account}")
		frappe.db.commit()
