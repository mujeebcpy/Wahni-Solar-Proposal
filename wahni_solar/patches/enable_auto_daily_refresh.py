import frappe


def execute():
	# A never-saved Check reads as 0; keep the daily refresh on for existing sites.
	singles = frappe.qb.DocType("Singles")
	stored = (
		frappe.qb.from_(singles)
		.select(singles.value)
		.where((singles.doctype == "Solar Monitor Settings") & (singles.field == "auto_daily_refresh"))
		.run()
	)
	if not stored:
		frappe.db.set_single_value("Solar Monitor Settings", "auto_daily_refresh", 1)
