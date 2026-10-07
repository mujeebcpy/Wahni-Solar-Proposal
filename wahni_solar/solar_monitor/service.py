"""Server-only Deye connector. Never expose provider response bodies in errors."""

import hashlib
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Coalesce
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password, set_encrypted_password
from redis.exceptions import LockError

ACCOUNT = "Solar API Account"
BASE_URLS = {
	"India": "https://india-developer.deyecloud.com",
	"Europe": "https://eu1-developer.deyecloud.com",
	"Americas": "https://us1-developer.deyecloud.com",
}


class ProviderError(frappe.ValidationError):
	pass


class InvalidToken(ProviderError):
	pass


class Busy(ProviderError):
	pass


def now():
	"""Current time in the site's System Settings time zone, used for all stored Datetime values."""
	return now_datetime()


def utcnow():
	"""Naive UTC, only for instants compared with provider timestamps or station time zones."""
	return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def lock(key, timeout, blocking_timeout, message=None):
	"""Redis lock that reports a held lock as a user-friendly Busy error instead of LockError."""
	held = frappe.cache().lock(key, timeout=timeout, blocking_timeout=blocking_timeout)
	if not held.acquire():
		raise Busy(message or _("This action is already in progress. Please wait a moment and try again."))
	try:
		yield
	finally:
		try:
			held.release()
		except LockError:
			# Lock expired after its timeout; nothing left to release.
			pass


def setting(key, default):
	return int(frappe.db.get_single_value("Solar Monitor Settings", key) or default)


def password_hash(password):
	return hashlib.sha256(password.encode("utf-8")).hexdigest()


def bearer(token):
	token = token.strip()
	if token.lower().startswith("bearer "):
		token = token[7:].strip()
	if not token or token.lower() == "bearer":
		raise ProviderError(_("Provider returned an empty access token."))
	return "Bearer " + token


def token_expiry(value, started):
	try:
		seconds = int(value)
	except (ValueError, TypeError, OverflowError):
		raise ProviderError(_("Provider returned an invalid token expiry.")) from None
	if seconds <= 0:
		raise ProviderError(_("Provider returned an invalid token expiry."))
	try:
		return started + timedelta(seconds=seconds)
	except OverflowError:
		raise ProviderError(_("Provider returned an invalid token expiry.")) from None


def account_doc(name):
	doc = frappe.get_doc(ACCOUNT, name)
	if not doc.enabled or doc.provider != "Deye":
		raise ProviderError(_("This account is disabled or its provider is not implemented."))
	return doc


def secret(doc, field):
	return get_decrypted_password(ACCOUNT, doc.name, field)


def pace(doc):
	key = "solar-monitor-rate:" + hashlib.sha256((doc.region + ":" + doc.app_id).encode()).hexdigest()
	cache = frappe.cache()
	with lock(key + ":lock", 20, 15, _("Application request queue is busy. Please try again shortly.")):
		delay = max(0, float(cache.get_value(key) or 0) - time.time())
		if delay > 10:
			raise ProviderError(_("Application request queue is busy. Please try again shortly."))
		time.sleep(delay)
		cache.set_value(key, time.time() + 60 / setting("requests_per_minute", 30), expires_in_sec=120)
	Account = frappe.qb.DocType(ACCOUNT)
	frappe.qb.update(Account).set(Account.request_count, Coalesce(Account.request_count, 0) + 1).where(
		Account.name == doc.name
	).run()


def post(doc, path, body, token=None):
	for attempt in range(3):
		pace(doc)
		headers = {"Content-Type": "application/json"}
		if token:
			headers["Authorization"] = bearer(token)
		try:
			response = requests.post(
				BASE_URLS[doc.region] + path,
				params={"appId": doc.app_id} if path.endswith("/token") else None,
				json=body,
				headers=headers,
				timeout=(10, 30),
				allow_redirects=False,
			)
		except requests.RequestException:
			raise ProviderError(_("Provider request failed or timed out.")) from None
		if response.status_code == 401 and token:
			raise InvalidToken(_("Provider rejected the access token."))
		if response.status_code == 429 or response.status_code >= 500:
			if attempt < 2:
				try:
					delay = float(response.headers.get("Retry-After", 2 ** (attempt + 1)))
				except ValueError:
					delay = 2 ** (attempt + 1)
				if delay > 30:
					raise ProviderError(_("Provider requested a longer retry delay. Try again later."))
				time.sleep(max(0, delay))
				continue
		if not 200 <= response.status_code < 300:
			raise ProviderError(_("Provider returned HTTP {0}.").format(response.status_code))
		try:
			data = response.json()
		except ValueError:
			raise ProviderError(_("Provider returned invalid JSON.")) from None
		if not isinstance(data, dict) or data.get("success") is not True:
			raise ProviderError(
				_(
					"Provider rejected the request. Verify credentials, company membership and access permissions."
				)
			)
		return data
	raise ProviderError(_("Provider is temporarily unavailable or rate limited."))


def ensure_token(name, rejected_token=None):
	with lock(
		"solar-monitor-token:" + name, 240, 15, _("Authentication is already in progress. Try again shortly.")
	):
		doc = account_doc(name)
		token = get_decrypted_password(ACCOUNT, name, "access_token", raise_exception=False)
		valid = (
			token
			and doc.expires_at
			and get_datetime(doc.expires_at) > now() + timedelta(seconds=setting("token_renewal_margin", 300))
		)
		if valid and (rejected_token is None or token != rejected_token):
			return token
		started = now()
		data = post(
			doc,
			"/v1.0/account/token",
			{
				"appSecret": secret(doc, "app_secret"),
				"email": doc.email,
				"password": password_hash(secret(doc, "password")),
				"companyId": int(doc.company_id),
			},
		)
		token = data.get("accessToken")
		if not isinstance(token, str):
			raise ProviderError(_("Provider response is missing the access token."))
		bearer(token)
		expiry = token_expiry(data.get("expiresIn"), started)
		refresh = data.get("refreshToken") or ""
		if not isinstance(refresh, str):
			raise ProviderError(_("Provider returned an invalid refresh token."))
		set_encrypted_password(ACCOUNT, name, token, "access_token")
		set_encrypted_password(ACCOUNT, name, refresh, "refresh_token")
		frappe.db.set_value(
			ACCOUNT,
			name,
			{
				"expires_at": expiry,
				"token_type": data.get("tokenType"),
				"scope": data.get("scope"),
				"provider_user_id": str(data.get("uid", "")),
				"last_authentication": started,
				"connection_status": "Connected",
				"authentication_error": "",
			},
		)
		frappe.db.commit()
		return token


def authenticated(name, path, body):
	token = ensure_token(name)
	try:
		return post(account_doc(name), path, body, token)
	except InvalidToken:
		token = ensure_token(name, rejected_token=token)
		return post(account_doc(name), path, body, token)


def company_details(name, manual=False):
	with lock("solar-monitor-company:" + name, 300, 15, _("Company details are already being fetched.")):
		doc = account_doc(name)
		if not manual and (doc.company_name or doc.company_lookup_attempted):
			return
		frappe.db.set_value(ACCOUNT, name, "company_lookup_attempted", 1)
		frappe.db.commit()
		try:
			data = authenticated(name, "/v1.0/account/info", {})
			organizations = data.get("orgInfoList")
			if not isinstance(organizations, list):
				raise ProviderError(_("Provider response is missing company memberships."))
			org = next(
				(x for x in organizations if str(x.get("companyId")) == str(int(doc.company_id))), None
			)
			if not org or not org.get("companyName"):
				raise ProviderError(_("No company name was returned for the configured Company ID."))
			frappe.db.set_value(
				ACCOUNT,
				name,
				{
					"company_name": org["companyName"],
					"company_details_fetched_at": now(),
					"company_lookup_error": "",
				},
			)
		except ProviderError as exc:
			frappe.db.set_value(ACCOUNT, name, "company_lookup_error", str(exc))
		frappe.db.commit()


def pages(name, path, key, body=None):
	result = []
	for page in range(1, 10001):
		data = authenticated(name, path, {**(body or {}), "page": page, "size": 100})
		items = data.get(key)
		if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
			raise ProviderError(_("Provider inventory response has an invalid list."))
		result.extend(items)
		try:
			total = int(data["total"])
		except (KeyError, TypeError, ValueError):
			raise ProviderError(_("Provider inventory response is missing its total count.")) from None
		if len(result) >= total:
			return result
		if not items:
			raise ProviderError(_("Provider pagination ended before all records were returned."))
	raise ProviderError(_("Provider inventory exceeded the pagination safety limit."))


def inventory_key(account, external_id):
	return hashlib.sha256((account + "\0" + str(external_id)).encode()).hexdigest()


def upsert(doctype, account, external_id, values, seen):
	key = inventory_key(account, external_id)
	name = frappe.db.get_value(doctype, {"inventory_key": key}, "name")
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.update(
		dict(
			account=account,
			external_id=str(external_id),
			inventory_key=key,
			present=1,
			last_seen=seen,
			**values,
		)
	)
	doc.save(ignore_permissions=True)
	return doc.name


def sync_job(account):
	try:
		with lock("solar-monitor-inventory:" + account, 7200, 1):
			_sync(account)
	except Busy:
		# Another worker is already syncing this account; it will update the status.
		pass


def _sync(account):
	try:
		account_doc(account)
		frappe.db.set_value(ACCOUNT, account, "sync_status", "Running")
		frappe.db.commit()
		ensure_token(account)
		company_details(account)
		stations = pages(account, "/v1.0/station/list", "stationList")
		devices = []
		for start in range(0, len(stations), 20):
			ids = [int(x["id"]) for x in stations[start : start + 20]]
			devices.extend(pages(account, "/v1.0/station/device", "deviceListItems", {"stationIds": ids}))
		seen = now()
		station_names = {}
		for row in stations:
			station_names[str(row["id"])] = upsert(
				"Solar Station",
				account,
				row["id"],
				{
					"station_name": row.get("name"),
					"timezone": row.get("regionTimezone"),
					"capacity_kw": row.get("installedCapacity"),
					"connection_status": row.get("connectionStatus"),
					"location": row.get("locationAddress"),
					"operating_since": operating_date(row.get("startOperatingTime")),
				},
				seen,
			)
		for row in devices:
			station = station_names.get(str(row["stationId"]))
			if not station or not row.get("deviceSn"):
				raise ProviderError(_("Provider returned a device with an unknown station or empty serial."))
			upsert(
				"Solar Device",
				account,
				row["deviceSn"],
				{"station": station, "device_type": row.get("deviceType")},
				seen,
			)
		for dt in ("Solar Station", "Solar Device"):
			table = frappe.qb.DocType(dt)
			frappe.qb.update(table).set(table.present, 0).where(
				(table.account == account) & (table.last_seen.isnull() | (table.last_seen < seen))
			).run()
		frappe.db.set_value(
			ACCOUNT, account, {"sync_status": "Completed", "last_successful_sync": seen, "sync_error": ""}
		)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback()
		if not isinstance(exc, ProviderError):
			frappe.log_error(title=f"Solar Monitor inventory sync failed: {account}")
		message = (
			str(exc)
			if isinstance(exc, ProviderError)
			else _("Inventory synchronization failed. Check configuration and worker availability.")
		)
		frappe.db.set_value(ACCOUNT, account, {"sync_status": "Failed", "sync_error": message})
		frappe.db.commit()


def operating_date(value):
	if not value:
		return None
	try:
		return datetime.fromtimestamp(float(value), timezone.utc).date()
	except (ValueError, TypeError, OverflowError, OSError):
		return None
