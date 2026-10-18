from datetime import date, datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from wahni_solar.solar_monitor import enphase as e


def account(**values):
	defaults = dict(name="acc", provider="Enphase", client_id="client", redirect_uri="", enphase_username="")
	return frappe._dict(defaults, **values)


class TestEnphase(FrappeTestCase):
	def test_authorize_url_uses_default_redirect(self):
		url = e.authorize_url(account(), "state1")
		self.assertTrue(url.startswith(e.OAUTH + "/authorize?"))
		self.assertIn("client_id=client", url)
		self.assertIn("state=state1", url)
		self.assertIn("redirect_uri=https%3A%2F%2Fapi.enphaseenergy.com%2Foauth%2Fredirect_uri", url)

	def test_authorization_code_accepts_pasted_url(self):
		self.assertEqual(e.authorization_code(" abc "), "abc")
		self.assertEqual(e.authorization_code(e.DEFAULT_REDIRECT_URI + "?code=xyz&state=s"), "xyz")
		for value in ["", None, "code=", "x" * 600]:
			with self.assertRaises(e.service.ProviderError):
				e.authorization_code(value)

	def test_token_request_uses_basic_auth_and_keeps_refresh(self):
		response = MagicMock()
		response.json.return_value = {"access_token": "new", "expires_in": 86393, "enl_uid": 7}
		with (
			patch.object(e.service, "secret", return_value="secret"),
			patch.object(e.service, "send", return_value=response) as send,
		):
			data = e.token_request(account(), params={"grant_type": "refresh_token"}, refresh="old")
			headers = send.call_args.kwargs["headers"]
			self.assertEqual(headers["Authorization"], "Basic Y2xpZW50OnNlY3JldA==")
			self.assertEqual(data["refresh_token"], "old")
			self.assertEqual((data["access_token"], data["uid"]), ("new", 7))

	def test_token_rejections_explain_which_credential(self):
		with patch.object(e.service, "secret", return_value="secret"):
			for status, expected in [(400, "custom"), (401, "Client ID or Client Secret")]:
				with patch.object(e.service, "send", side_effect=e.service.ProviderHTTPError("HTTP", status)):
					with self.assertRaises(e.service.ProviderHTTPError) as raised:
						e.token_request(account(), data={}, rejected="custom")
					self.assertIn(expected, str(raised.exception))
					self.assertEqual(raised.exception.status, status)

	def test_rejected_refresh_falls_back_to_password_grant(self):
		doc = account(enphase_username="installer@example.invalid")
		with (
			patch.object(e, "get_decrypted_password", side_effect=["refresh", "pass"]),
			patch.object(
				e,
				"token_request",
				side_effect=[e.service.ProviderHTTPError("bad", 400), {"access_token": "t"}],
			) as request,
		):
			self.assertEqual(e.renew_token(doc)["access_token"], "t")
			self.assertEqual(request.call_args.kwargs["data"]["grant_type"], "password")

	def test_missing_authorization_asks_to_authorize(self):
		with (
			patch.object(e, "get_decrypted_password", return_value=None),
			patch.object(e, "token_request") as req,
		):
			with self.assertRaises(e.service.ProviderError):
				e.renew_token(account())
			req.assert_not_called()

	def test_refresh_server_error_is_not_masked(self):
		with (
			patch.object(e, "get_decrypted_password", return_value="refresh"),
			patch.object(e, "token_request", side_effect=e.service.ProviderHTTPError("down", 500)),
		):
			with self.assertRaises(e.service.ProviderHTTPError):
				e.renew_token(account())

	def test_inventory_maps_systems_and_active_devices(self):
		systems = [
			{
				"system_id": 11,
				"name": "Home",
				"timezone": "Asia/Kolkata",
				"status": "normal",
				"address": {"city": "Kochi", "state": "KL", "country": "IN"},
				"operational_at": 1767225600,
				"system_size": -1,
			}
		]
		devices = {
			"devices": {
				"micros": [
					{"serial_number": "M1", "active": True},
					{"serial_number": "M2", "active": False},
				],
				"gateways": [{"serial_number": "G1"}],
				"heat_pump": [{"serial_number": ""}],
			}
		}
		with (
			patch.object(e.service, "pages", return_value=systems),
			patch.object(e.service, "authenticated", return_value=devices),
		):
			stations, found = e.inventory("acc")
		values = stations[0][1]
		self.assertEqual(stations[0][0], 11)
		self.assertEqual(values["connection_status"], "System Normal")
		self.assertEqual(values["location"], "Kochi, KL, IN")
		self.assertNotIn("capacity_kw", values)
		self.assertEqual(found, [(11, "M1", "Microinverter"), (11, "G1", "Gateway")])

	def test_snapshot_converts_watts_and_adds_today(self):
		station = frappe._dict(account="acc", external_id="11", timezone="Asia/Kolkata")
		summary = {
			"current_power": 2500,
			"energy_today": 4000,
			"energy_lifetime": 1000000,
			"size_w": 5000,
			"status": "normal",
			"summary_date": "2026-10-06",
			"last_report_at": 1791000000,
		}
		with patch.object(
			e.service, "authenticated", side_effect=[summary, {"production": [10000, 0, 5000, 1000, 0]}]
		) as call:
			data = e.snapshot(station)
			params = call.call_args.args[2]
		self.assertEqual(params, {"start_date": "2026-10-01", "end_date": "2026-10-05"})
		self.assertEqual(data["production_power_kw"], 2.5)
		self.assertEqual(data["daily_production_kwh"], 4)
		self.assertEqual(data["monthly_production_kwh"], 20)
		self.assertEqual(data["total_production_kwh"], 1004)
		self.assertEqual(data["capacity_kw"], 5)
		self.assertEqual(data["production_date"], date(2026, 10, 6))
		self.assertEqual(data["source_updated_at"], "1791000000")
		self.assertEqual((data["has_power"], data["has_monthly"]), (1, 1))

	def test_snapshot_first_of_month_needs_one_call(self):
		station = frappe._dict(account="acc", external_id="11", timezone="Asia/Kolkata")
		summary = {
			"current_power": None,
			"energy_today": 500,
			"energy_lifetime": None,
			"summary_date": "2026-10-01",
		}
		with patch.object(e.service, "authenticated", return_value=summary) as call:
			data = e.snapshot(station)
		self.assertEqual(call.call_count, 1)
		self.assertEqual(data["monthly_production_kwh"], 0.5)
		self.assertIsNone(data["total_production_kwh"])
		self.assertEqual((data["has_power"], data["has_total"]), (0, 0))
		self.assertNotIn("capacity_kw", data)

	def test_alarm_severity_and_devices(self):
		names = {"28": {"name": "Gateway not reporting", "key": "envoy_no_report"}}
		with patch.object(e.alerts, "get_system_timezone", return_value="Asia/Kolkata"):
			values = e.alarm_values(
				{
					"id": "a1",
					"event_type_id": 28,
					"severity": 2,
					"alarm_start_time": 1767225600,
					"events": [{"serial_number": "S1"}, {"serial_number": "S2"}],
				},
				names,
			)
		self.assertEqual(
			(values["severity"], values["level"], values["priority"]), ("Critical", "Failure", 3)
		)
		self.assertEqual(values["alert_name"], "Gateway not reporting")
		self.assertEqual(values["device_sn"], "S1 (+1)")
		self.assertEqual(values["alert_start"], datetime(2026, 1, 1, 5, 30))
		self.assertEqual(e.alarm_values({"severity": 4, "event_type_id": 9}, {})["severity"], "Notice")
		self.assertEqual(e.alarm_values({"severity": 3}, {})["severity"], "Warning")

	def test_monthly_quota_is_not_retried(self):
		response = MagicMock(status_code=429, headers={})
		response.json.return_value = {"message": "Too Many Requests", "period": "month"}
		with (
			patch.object(e.service, "pace"),
			patch.object(e.service.requests, "request", return_value=response) as request,
		):
			with self.assertRaises(e.service.ProviderError) as raised:
				e.service.send(account(), "GET", e.API + "/systems")
			self.assertIn("monthly", str(raised.exception))
			self.assertEqual(request.call_count, 1)

	def test_forbidden_reports_plan_limit(self):
		response = MagicMock(status_code=403, headers={})
		with (
			patch.object(e.service, "pace"),
			patch.object(e.service.requests, "request", return_value=response),
		):
			with self.assertRaises(e.service.ProviderHTTPError) as raised:
				e.service.send(account(), "GET", e.API + "/systems")
			self.assertEqual(raised.exception.status, 403)

	def test_authenticated_uses_get_with_api_key(self):
		response = MagicMock(status_code=200)
		response.json.return_value = {"system_id": 11}
		with (
			patch.object(e.service, "ensure_token", return_value="tok"),
			patch.object(e.service, "account_doc", return_value=account()),
			patch.object(e.service, "secret", return_value="apikey"),
			patch.object(e.service, "pace"),
			patch.object(e.service.requests, "request", return_value=response) as request,
		):
			self.assertEqual(e.service.authenticated("acc", "/systems/11/summary", {})["system_id"], 11)
			args, kwargs = request.call_args
			self.assertEqual(args, ("GET", e.API + "/systems/11/summary"))
			self.assertEqual(kwargs["headers"]["key"], "apikey")
			self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")
			self.assertIsNone(kwargs["params"])

	def test_check_station_closes_alarms_no_longer_open(self):
		station = frappe._dict(name="Home", external_id="11")
		rows = {"alarms": [{"id": "a1", "event_type_id": 28, "severity": 4}]}
		with (
			patch.object(e.service, "now", return_value=datetime(2026, 10, 6, 12)),
			patch.object(e.service, "authenticated", return_value=rows),
			patch.object(e, "event_types", return_value={}),
			patch.object(e.alerts, "save") as save,
			patch.object(e.alerts, "close_missing") as close,
		):
			e.check_station("acc", station)
			self.assertEqual(save.call_args.args[2], e.alerts.hashed("acc", "enphase-alarm:a1"))
			close.assert_called_once_with("Home", datetime(2026, 10, 6, 12))
