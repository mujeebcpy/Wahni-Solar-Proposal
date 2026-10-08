from contextlib import nullcontext
from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from wahni_solar.solar_monitor import alerts as a


class TestAlerts(FrappeTestCase):
	def test_severity_puts_safety_and_failures_first(self):
		self.assertEqual(a.severity(2, 1), "Critical")
		self.assertEqual(a.severity(3, 0), "Critical")
		self.assertEqual(a.severity(0, 2), "Critical")
		self.assertEqual(a.severity(1, 0), "Warning")
		self.assertEqual(a.severity(0, 1), "Warning")
		self.assertEqual(a.severity(0, 0), "Notice")
		self.assertEqual(a.severity(None, None), "Notice")

	def test_provider_timestamps_accept_seconds_and_milliseconds(self):
		with patch.object(a, "get_system_timezone", return_value="Asia/Kolkata"):
			self.assertEqual(a.site_datetime(1767225600), datetime(2026, 1, 1, 5, 30))
			self.assertEqual(a.site_datetime(1767225600000), datetime(2026, 1, 1, 5, 30))
			for value in [None, "", "bad", 0, -5]:
				self.assertIsNone(a.site_datetime(value))

	def test_station_alerts_paginate_and_accept_empty_list(self):
		pages = [
			{"stationAlertItems": [{"alertId": "1"}], "total": 2},
			{"stationAlertItems": [{"alertId": "2"}], "total": 2},
		]
		with patch.object(a.service, "authenticated", side_effect=pages) as call:
			self.assertEqual(len(a.station_alerts("acc", "12", 1, 2)), 2)
			body = call.call_args.args[2]
			self.assertEqual((body["stationId"], body["page"], body["size"]), (12, 2, 200))
		with patch.object(a.service, "authenticated", return_value={"stationAlertItems": None, "total": 0}):
			self.assertEqual(a.station_alerts("acc", "12", 1, 2), [])
		with patch.object(a.service, "authenticated", return_value={"stationAlertItems": "bad", "total": 1}):
			with self.assertRaises(a.service.ProviderError):
				a.station_alerts("acc", "12", 1, 2)

	def test_alert_key_is_stable_without_provider_id(self):
		row = {"deviceSn": "SN1", "alertCode": "35", "alertStartTime": 100}
		self.assertEqual(a.alert_key("acc", row), a.alert_key("acc", dict(row)))
		self.assertNotEqual(a.alert_key("acc", row), a.alert_key("other", row))

	def test_pending_alert_check_is_reused(self):
		doc = frappe._dict(alert_status="Running", alert_started_at=datetime(2026, 10, 6, 12))
		fake = MagicMock()
		with (
			patch.object(a, "frappe", fake),
			patch.object(a.service, "lock", return_value=nullcontext()),
			patch.object(a.service, "account_doc", return_value=doc),
			patch.object(a.service, "now", return_value=datetime(2026, 10, 6, 12, 5)),
		):
			self.assertEqual(a.enqueue("acc")["status"], "Running")
			fake.enqueue.assert_not_called()

	def test_one_failing_station_does_not_discard_others(self):
		stations = [frappe._dict(name="A", external_id="1"), frappe._dict(name="B", external_id="2")]
		with (
			patch.object(a.frappe, "db", new=MagicMock()) as db,
			patch.object(a.frappe, "get_all", return_value=stations),
			patch.object(a.service, "account_doc"),
			patch.object(a.service, "setting", return_value=30),
			patch.object(a.service, "now", return_value=datetime(2026, 10, 6, 12)),
			patch.object(a, "check_station", side_effect=[a.service.ProviderError("down"), None]),
		):
			a._check("acc")
			final = db.set_value.call_args.args[2]
			self.assertEqual(final["alert_status"], "Completed")
			self.assertIn("A", final["alert_error"])
