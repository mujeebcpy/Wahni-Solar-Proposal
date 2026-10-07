import hashlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from wahni_solar.solar_monitor import service as s


class TestService(FrappeTestCase):
	def test_hash_preserves_password(self):
		value = " pass  café "
		self.assertEqual(s.password_hash(value), hashlib.sha256(value.encode()).hexdigest())
		self.assertNotEqual(s.password_hash(value), s.password_hash(value.strip()))

	def test_bearer(self):
		self.assertEqual(s.bearer("Bearer abc"), "Bearer abc")
		self.assertEqual(s.bearer("abc"), "Bearer abc")
		with self.assertRaises(s.ProviderError):
			s.bearer("Bearer ")

	def test_expiry(self):
		now = datetime(2026, 1, 1)
		self.assertEqual(s.token_expiry("100", now), now + timedelta(seconds=100))
		self.assertEqual(s.token_expiry(100, now), now + timedelta(seconds=100))
		for value in [None, "bad", 0, -1]:
			with self.assertRaises(s.ProviderError):
				s.token_expiry(value, now)

	def test_valid_token_reused(self):
		cache = MagicMock()
		doc = MagicMock(expires_at=s.now() + timedelta(hours=1))
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s, "account_doc", return_value=doc),
			patch.object(s, "get_decrypted_password", return_value="saved"),
			patch.object(s, "setting", return_value=300),
			patch.object(s, "post") as post,
		):
			self.assertEqual(s.ensure_token("a"), "saved")
			post.assert_not_called()

	def test_company_skipped_when_saved_or_attempted(self):
		cache = MagicMock()
		for name, attempted in [("Saved", 0), ("", 1)]:
			doc = MagicMock(company_name=name, company_lookup_attempted=attempted)
			with (
				patch.object(s.frappe, "cache", return_value=cache),
				patch.object(s, "account_doc", return_value=doc),
				patch.object(s, "authenticated") as call,
			):
				s.company_details("a")
				call.assert_not_called()

	def test_pagination(self):
		with patch.object(
			s,
			"authenticated",
			side_effect=[{"stationList": [{"id": 1}], "total": 2}, {"stationList": [{"id": 2}], "total": 2}],
		) as call:
			self.assertEqual(len(s.pages("a", "/list", "stationList")), 2)
			self.assertEqual(call.call_args.args[2]["page"], 2)
		with patch.object(s, "authenticated", return_value={"stationList": [], "total": 2}):
			with self.assertRaises(s.ProviderError):
				s.pages("a", "/list", "stationList")

	def test_invalid_token_retry_only_once(self):
		with (
			patch.object(s, "ensure_token", side_effect=["old", "new"]) as token,
			patch.object(s, "account_doc"),
			patch.object(s, "post", side_effect=[s.InvalidToken("expired"), {"success": True}]) as post,
		):
			self.assertTrue(s.authenticated("a", "/list", {})["success"])
			self.assertEqual(post.call_count, 2)
			token.assert_called_with("a", rejected_token="old")

	def test_provider_error_does_not_renew(self):
		with (
			patch.object(s, "ensure_token", return_value="old") as token,
			patch.object(s, "account_doc"),
			patch.object(s, "post", side_effect=s.ProviderError("denied")),
		):
			with self.assertRaises(s.ProviderError):
				s.authenticated("a", "/list", {})
			self.assertEqual(token.call_count, 1)

	def test_near_expiry_reauthenticates_and_saves_secrets(self):
		cache = MagicMock()
		doc = MagicMock(
			expires_at=s.now() + timedelta(seconds=30), company_id="123", email="a@example.invalid"
		)
		data = {"accessToken": "new", "refreshToken": "refresh", "expiresIn": "3600", "tokenType": "bearer"}
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s.frappe, "db", new=MagicMock()) as db,
			patch.object(s, "account_doc", return_value=doc),
			patch.object(s, "get_decrypted_password", return_value="old"),
			patch.object(s, "secret", return_value=" normal "),
			patch.object(s, "setting", return_value=300),
			patch.object(s, "post", return_value=data) as post,
			patch.object(s, "set_encrypted_password") as save,
		):
			self.assertEqual(s.ensure_token("a"), "new")
			self.assertEqual(post.call_args.args[2]["password"], s.password_hash(" normal "))
			self.assertEqual(save.call_count, 2)
			db.commit.assert_called_once()

	def test_manual_company_lookup_matches_id(self):
		cache = MagicMock()
		doc = MagicMock(company_name="Old", company_lookup_attempted=1, company_id="123")
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s.frappe, "db", new=MagicMock()) as db,
			patch.object(s, "account_doc", return_value=doc),
			patch.object(
				s,
				"authenticated",
				return_value={
					"orgInfoList": [
						{"companyId": 99, "companyName": "Other"},
						{"companyId": 123, "companyName": "Correct"},
					]
				},
			),
		):
			s.company_details("a", manual=True)
			self.assertEqual(db.set_value.call_args.args[2]["company_name"], "Correct")

	def test_failed_company_lookup_keeps_authentication(self):
		cache = MagicMock()
		doc = MagicMock(company_name="", company_lookup_attempted=0, company_id="123")
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s.frappe, "db", new=MagicMock()) as db,
			patch.object(s, "account_doc", return_value=doc),
			patch.object(s, "authenticated", side_effect=s.ProviderError("Unavailable")),
		):
			s.company_details("a")
			self.assertEqual(db.set_value.call_args.args[2], "company_lookup_error")

	def test_failed_inventory_rolls_back_without_marking_missing(self):
		cache = MagicMock()
		with (
			patch.object(s.frappe, "cache", return_value=cache),
			patch.object(s.frappe, "db", new=MagicMock()) as db,
			patch.object(s, "account_doc"),
			patch.object(s, "ensure_token"),
			patch.object(s, "company_details"),
			patch.object(s, "pages", side_effect=s.ProviderError("Unavailable")),
			patch.object(s, "upsert") as upsert,
		):
			s.sync_job("a")
			db.rollback.assert_called_once()
			upsert.assert_not_called()
			db.sql.assert_not_called()
			self.assertEqual(db.set_value.call_args.args[2]["sync_status"], "Failed")

	def test_held_lock_is_reported_as_busy(self):
		cache = MagicMock()
		cache.lock.return_value.acquire.return_value = False
		with patch.object(s.frappe, "cache", return_value=cache):
			with self.assertRaises(s.Busy), s.lock("key", 10, 1, "Already running."):
				pass
		cache.lock.return_value.release.assert_not_called()

	def test_busy_inventory_job_is_skipped(self):
		with patch.object(s, "lock", side_effect=s.Busy("busy")), patch.object(s, "_sync") as sync:
			s.sync_job("a")
			sync.assert_not_called()
