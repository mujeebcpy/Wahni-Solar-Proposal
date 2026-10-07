from datetime import date, datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from wahni_solar.solar_monitor import production as p


class TestProduction(FrappeTestCase):
	def test_numeric_values_and_missing_readings(self):
		self.assertEqual(p.number("2.5"), 2.5)
		for x in [None, "", "NaN", "Infinity", True]:
			self.assertIsNone(p.number(x))
		self.assertIsNone(p.energy([]))
		self.assertIsNone(p.energy([{"generationValue": None}]))
		self.assertEqual(p.energy([{"generationValue": 0}]), 0)

	def test_station_timezone_day_boundary(self):
		with patch.object(p.service, "utcnow", return_value=datetime(2026, 10, 6, 20)):
			self.assertEqual(p.local_date(frappe._dict(timezone="Asia/Kolkata")), date(2026, 10, 7))

	def test_snapshot_uses_daily_and_annual_history(self):
		station = frappe._dict(
			account="account", external_id="123", timezone="Asia/Kolkata", operating_since="2024-01-01"
		)
		days = [
			{"year": 2026, "month": 10, "day": 5, "generationValue": 10},
			{"year": 2026, "month": 10, "day": 6, "generationValue": 20},
		]
		years = [
			{"year": 2024, "generationValue": 100},
			{"year": 2025, "generationValue": 200},
			{"year": 2026, "generationValue": 30},
		]
		with (
			patch.object(p, "local_date", return_value=date(2026, 10, 6)),
			patch.object(
				p.service, "authenticated", return_value={"generationPower": 2500, "lastUpdateTime": 123}
			),
			patch.object(p, "history", side_effect=[days, years]) as history,
		):
			data = p.snapshot(station)
			self.assertEqual(data["production_power_kw"], 2.5)
			self.assertEqual(data["daily_production_kwh"], 20)
			self.assertEqual(data["monthly_production_kwh"], 30)
			self.assertEqual(data["total_production_kwh"], 330)
			self.assertEqual(history.call_args_list[0].args[1]["endAt"], "2026-10-07")
			self.assertEqual(history.call_args_list[1].args[1]["startAt"], "2024")

	def test_previous_day_is_not_todays_production(self):
		row = frappe._dict(
			timezone="Asia/Kolkata",
			production_date="2026-09-30",
			has_power=1,
			has_daily=1,
			has_monthly=1,
			has_total=1,
			production_power_kw=2,
			daily_production_kwh=20,
			monthly_production_kwh=300,
			total_production_kwh=1000,
			last_production_fetch=None,
		)
		with patch.object(p, "local_date", return_value=date(2026, 10, 1)):
			result = p.display(row)
			self.assertIsNone(result.production_power_kw)
			self.assertIsNone(result.daily_production_kwh)
			self.assertIsNone(result.monthly_production_kwh)
			self.assertEqual(result.total_production_kwh, 1000)
			self.assertTrue(result.stale)

	def test_totals_include_all_readings_and_report_coverage(self):
		rows = [
			frappe._dict(
				capacity_kw=5,
				connection_status="NORMAL",
				stale=False,
				production_power_kw=1,
				daily_production_kwh=10,
				total_production_kwh=100,
			),
			frappe._dict(
				capacity_kw=3,
				connection_status="OFFLINE",
				stale=True,
				production_power_kw=None,
				daily_production_kwh=None,
				total_production_kwh=50,
			),
		]
		result = p.totals(rows)
		self.assertEqual(result["capacity_kw"], 8)
		self.assertEqual(result["daily_production_kwh"], 10)
		self.assertEqual(result["daily_production_kwh_coverage"], 1)
		self.assertEqual(result["total_production_kwh"], 150)
		self.assertEqual(result["stale_count"], 1)

	def test_recent_request_reuses_saved_readings(self):
		from contextlib import nullcontext
		from unittest.mock import MagicMock

		fake = MagicMock()
		fake.get_doc.return_value = frappe._dict(
			account="a",
			present=1,
			production_status="Completed",
			production_requested_at=datetime(2026, 10, 6, 12),
		)
		with (
			patch.object(p, "frappe", fake),
			patch.object(p.service, "account_doc"),
			patch.object(p.service, "lock", return_value=nullcontext()),
			patch.object(p.service, "now", return_value=datetime(2026, 10, 6, 12, 1)),
			patch.object(p.service, "setting", return_value=300),
		):
			result = p.enqueue("Station")
			self.assertEqual(result["status"], "Cached")
			fake.enqueue.assert_not_called()

	def test_pending_production_job_is_reused(self):
		from contextlib import nullcontext
		from unittest.mock import MagicMock

		fake = MagicMock()
		fake.get_doc.return_value = frappe._dict(
			account="a",
			present=1,
			production_status="Queued",
			production_requested_at=datetime(2026, 10, 6, 12),
		)
		with (
			patch.object(p, "frappe", fake),
			patch.object(p.service, "account_doc"),
			patch.object(p.service, "lock", return_value=nullcontext()),
			patch.object(p.service, "now", return_value=datetime(2026, 10, 6, 12, 1)),
		):
			self.assertEqual(p.enqueue("Station")["status"], "Queued")
			fake.enqueue.assert_not_called()

	def test_history_omits_inventory_pagination_and_rejects_truncation(self):
		body = {"stationId": 123, "granularity": 2, "startAt": "2026-10-01", "endAt": "2026-10-07"}
		with patch.object(
			p.service,
			"authenticated",
			return_value={"total": 1, "stationDataItems": [{"generationValue": 1}]},
		) as call:
			self.assertEqual(len(p.history("a", body)), 1)
			self.assertEqual(call.call_args.args[2], body)
			self.assertNotIn("size", call.call_args.args[2])
		with patch.object(p.service, "authenticated", return_value={"total": 2, "stationDataItems": []}):
			with self.assertRaises(p.service.ProviderError):
				p.history("a", body)
