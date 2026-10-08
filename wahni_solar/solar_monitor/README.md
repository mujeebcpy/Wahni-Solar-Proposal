# Solar Monitor — Phase 1

Open the Solar Monitor workspace, then Solar API Account. Create a Deye account with region, app ID, app secret, email, **normal password**, and company ID. Save and use **Test Connection**, then **Fetch Stations & Devices**. Workers must be running; inventory is fetched on the long queue. Dashboard navigation reads saved records only.

Company details are fetched once when missing during the first successful connection/fetch. Failed discovery does not break authentication or repeat automatically. Use **Fetch / Update Company Details** to retry or update. Company names are Deye-only display labels; API calls use company/station IDs and tokens.

Access and refresh tokens are encrypted Password values, never returned by dashboard methods. Access tokens are reused until five minutes before expiry. Phase 1 renews through the documented login endpoint with saved credentials; refresh-token exchange is intentionally not assumed. No scheduled token or inventory polling is enabled. API secrets and the site's encryption key must be included in appropriate protected backup procedures.

Solar Monitor Settings controls cooldown (120 seconds), renewal margin (300 seconds), and app/region request rate (30/minute). The configured rate applies across account records sharing application credentials. HTTP 429/5xx requests use bounded backoff. Pending inventory jobs are reused for up to two hours before stale job recovery.

System Managers manage credentials and fetch. Assign Solar Monitor Viewer (shipped as a Role fixture) for read-only inventory/dashboard access. This role grants site-wide Solar Monitor inventory visibility; Project-specific permissions are a later phase. Enphase and Solarman accounts can be saved disabled for future use. Their integrations, alerts, and Project mapping are not implemented yet. Deye production snapshots are available as described below.

Tests (inside the existing container):

```sh
docker exec -w /home/frappe/frappe-bench erp bench --site <site> run-tests --module wahni_solar.solar_monitor.tests.test_service
docker exec -w /home/frappe/frappe-bench erp bench --site <site> run-tests --module wahni_solar.solar_monitor.tests.test_production
docker exec -w /home/frappe/frappe-bench erp bench --site <site> run-tests --module wahni_solar.solar_monitor.tests.test_alerts
```

The workspace route is `/app/solar-monitor`; its Dashboard shortcut opens the separate custom Page at `/app/solar-monitor-dashboard`.

## Production dashboard

API accounts are named by their Account Label. Station names are used for station record names; device names use `device type - station name`. Collisions get a numeric suffix (`Plant-1`). The identity key still uses account plus external identifier, so repeat imports update existing records.

Fetch inventory after a reset, then click **Update production** to queue all enabled Deye stations or use a station row's **Update** button. Click a station name for saved production details and its devices. Station forms also provide **Update Production**.

Cards aggregate all present stations in the selected account/provider, independent of the table's pagination or search. Readings show coverage and stale counts; missing energy is not displayed as zero. Today/month rollover follows station timezone. Individual updates use a configurable 300-second cooldown and pending-job reuse. Workers query latest power, current month's daily energy and annual energy since commissioning (or year 2000 when no commissioning date is available). Lifetime production is the sum of annual readings returned by the provider. No production requests happen on navigation.

All timestamps are stored and shown in the site time zone (System Settings → Time Zone, e.g. Asia/Kolkata for UTC+05:30). Station today/month rollover still follows each station's own time zone.

## Alerts

The dashboard shows open alerts first. **Check alerts** queues one long-queue job per enabled Deye account (or the selected account) that calls `/v1.0/station/alertList` for every present station, covering the last *Alert Lookback* days (Solar Monitor Settings, default 30, Deye maximum 180). Alerts are saved as Solar Alert records and nothing is polled automatically. A failing station is reported on the account without discarding the stations that succeeded.

Severity comes from Deye's `impact` (0 none, 1 production, 2 safety, 3 production & safety) and `level` (0 notice, 1 warning, 2 failure):

- **Critical** (needs immediate installer attention): safety impact (2 or 3) or failure level (2).
- **Warning**: production impact (1) or warning level (1).
- **Notice**: everything else.

Open alerts are listed Critical first, then newest first. Open alerts inside the checked window that Deye no longer returns are closed.
