"""API hit budget and the daily scheduler."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from wahni_solar.solar_monitor import enphase, schedule
from wahni_solar.solar_monitor import service as s


def account(**values):
	return frappe._dict(
		dict(
			name="acc",
			provider="Enphase",
			client_id="client",
			region=None,
			app_id=None,
			month_hits=0,
			month_hits_period=None,
		),
		**values,
	)


class TestUsage(IntegrationTestCase):
	def test_budget_blocks_enphase_calls_only(self):
		with (
			patch.object(s, "setting", return_value=9000),
			patch.object(s, "month_hits", return_value=9000),
		):
			with self.assertRaises(s.ProviderError):
				s.check_budget(account())
			s.check_budget(account(provider="Deye", region="India", app_id="x"))

	def test_counter_falls_back_to_saved_value_in_same_month(self):
		cache = MagicMock()
		cache.get.return_value = None
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s, "now", return_value=datetime(2026, 10, 30)),
		):
			self.assertEqual(s.month_hits(account(month_hits=42, month_hits_period="2026-10")), 42)
			self.assertEqual(s.month_hits(account(month_hits=42, month_hits_period="2026-09")), 0)

	def test_hits_are_counted_per_application(self):
		self.assertEqual(s.app_identity(account()), s.app_identity(account(name="other")))
		self.assertNotEqual(s.app_identity(account()), s.app_identity(account(client_id="another")))

	def test_token_requests_are_not_counted(self):
		response = MagicMock(status_code=200)
		response.json.return_value = {"access_token": "t", "expires_in": 60}
		with (
			patch.object(s, "pace") as pace,
			patch.object(s.requests, "request", return_value=response),
			patch.object(s, "secret", return_value="secret"),
		):
			enphase.token_request(account(), params={"grant_type": "refresh_token"})
		self.assertEqual(pace.call_args.args[1], False)

	def test_daily_refresh_skips_refused_and_exhausted_accounts(self):
		calls = []

		def account_doc(name):
			if name == "revoked":
				raise s.ProviderError("owner not eligible")
			return account(name=name)

		def check_budget(doc):
			if doc.name == "exhausted":
				raise s.ProviderError("budget")

		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == s.ACCOUNT:
				return ["ok", "revoked", "exhausted"]
			return [f"{filters['account']}-station"]

		with (
			patch.object(schedule.frappe.db, "get_single_value", return_value=1),
			patch.object(schedule.frappe, "get_all", side_effect=get_all),
			patch.object(schedule.frappe.db, "commit"),
			patch.object(s, "account_doc", side_effect=account_doc),
			patch.object(s, "check_budget", side_effect=check_budget),
			patch.object(s, "now", return_value=datetime(2026, 11, 1, 19)),  # a Sunday
			patch.object(schedule.production, "enqueue", side_effect=lambda st: calls.append(st)),
			patch.object(schedule.alerts, "enqueue") as alert_enqueue,
		):
			schedule.daily_refresh()
		self.assertEqual(calls, ["ok-station"])
		alert_enqueue.assert_called_once_with("ok", full=True)

	def test_daily_refresh_does_nothing_when_turned_off(self):
		with (
			patch.object(schedule.frappe.db, "get_single_value", return_value=0),
			patch.object(schedule.frappe, "get_all") as get_all,
		):
			schedule.daily_refresh()
		get_all.assert_not_called()
