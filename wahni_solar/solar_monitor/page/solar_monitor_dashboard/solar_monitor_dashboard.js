frappe.pages["solar-monitor-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Solar Monitor"),
		single_column: true,
	});
	const body = $('<div class="solar-monitor-dashboard p-3"></div>').appendTo(page.body);
	$("<style>")
		.text(
			`
 .solar-monitor-dashboard .sm-cards {display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:24px}
 .solar-monitor-dashboard .sm-card {padding:18px;border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg)}
 .solar-monitor-dashboard .sm-card:nth-child(1) {border-top:3px solid #597ef7}
 .solar-monitor-dashboard .sm-card:nth-child(2) {border-top:3px solid #9254de}
 .solar-monitor-dashboard .sm-card:nth-child(3) {border-top:3px solid #13c2c2}
 .solar-monitor-dashboard .sm-card:nth-child(4) {border-top:3px solid #52c41a}
 .solar-monitor-dashboard .sm-card:nth-child(5) {border-top:3px solid #faad14}
 .solar-monitor-dashboard .sm-value {font-size:26px;font-weight:600;margin:8px 0}
 .solar-monitor-dashboard .sm-note {font-size:12px;color:var(--text-muted)}
 .solar-monitor-dashboard .sm-station {font-weight:600;text-align:left}
 .solar-monitor-dashboard td {vertical-align:middle}
 `
		)
		.appendTo(body);
	let offset = 0,
		timer,
		generation = 0,
		account,
		search;
	const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
	const fetched = (value) => (value ? frappe.datetime.str_to_user(value) : __("Never"));
	const format = (value, unit = "") =>
		value == null
			? "—"
			: `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`;
	const call = (method, args, type = "POST") =>
		frappe.call({ method: `wahni_solar.solar_monitor.api.${method}`, args, type });
	const provider = page.add_field({
		fieldname: "provider",
		label: __("Provider"),
		fieldtype: "Select",
		options: "Deye\nEnphase\nSolarman",
		default: "Deye",
		change() {
			if (!account) return;
			offset = 0;
			account.set_value("");
			load();
		},
	});
	account = page.add_field({
		fieldname: "account",
		label: __("Account"),
		fieldtype: "Select",
		options: "",
		change() {
			if (!search) return;
			offset = 0;
			load();
		},
	});
	search = page.add_field({
		fieldname: "search",
		label: __("Station name"),
		fieldtype: "Data",
		change() {
			offset = 0;
			load();
		},
	});
	const cardDefs = [
		["production_power_kw", "Current generating power", "kW"],
		["capacity_kw", "Installed capacity", "kWp"],
		["daily_production_kwh", "Today’s production", "kWh"],
		["monthly_production_kwh", "This month’s production", "kWh"],
		["total_production_kwh", "Lifetime production", "kWh"],
	];
	function cards(summary) {
		const cards = $('<div class="sm-cards"></div>').appendTo(body);
		cardDefs.forEach(([field, label, unit]) => {
			const coverage = summary[field + "_coverage"];
			cards.append(
				`<div class="sm-card"><div>${esc(__(label))}</div><div class="sm-value">${esc(
					format(summary[field], unit)
				)}</div><div class="sm-note">${esc(
					field === "capacity_kw"
						? __("{0} stations", [summary.station_count])
						: __("{0}/{1} stations with readings", [
								coverage ?? 0,
								summary.station_count,
						  ])
				)}</div></div>`
			);
		});
	}
	async function update(station, button) {
		if (button) button.prop("disabled", true);
		try {
			const r = await call("refresh_station", { station });
			if (r.message.status === "Cached")
				frappe.show_alert({
					message: __("Saved reading reused. Try again in {0} seconds.", [
						r.message.retry_after,
					]),
					indicator: "blue",
				});
			else
				frappe.show_alert({
					message: __("Production update {0}.", [r.message.status.toLowerCase()]),
					indicator: "blue",
				});
			await load();
		} finally {
			if (button) button.prop("disabled", false);
		}
	}
	async function details(name) {
		const r = await call("get_station", { station: name }, "GET"),
			s = r.message.station;
		const dialog = new frappe.ui.Dialog({
			title: s.station_name || s.name,
			size: "large",
			fields: [{ fieldname: "details", fieldtype: "HTML" }],
		});
		const content = dialog.fields_dict.details.$wrapper;
		content.html(
			`<p>${esc(s.location || "")} · ${esc(
				s.connection_status || __("Unknown status")
			)}</p><div class="row">${cardDefs
				.map(
					([field, label, unit]) =>
						`<div class="col-sm-6 mb-3"><div class="text-muted">${esc(
							__(label)
						)}</div><strong>${esc(format(s[field], unit))}</strong></div>`
				)
				.join("")}</div><p class="text-muted">${esc(__("Last fetched"))}: ${esc(
				fetched(s.last_production_fetch)
			)}<br>${esc(__("Provider timestamp"))}: ${esc(s.source_updated_at || "—")}<br>${esc(
				s.stale ? __("Saved readings may be stale.") : __("Saved readings")
			)}</p><p class="text-danger">${esc(s.production_error || "")}</p><h5>${esc(
				__("Devices")
			)}</h5>`
		);
		r.message.devices.forEach((d) =>
			$("<p>")
				.append(
					$("<a>")
						.attr("href", "/app/solar-device/" + encodeURIComponent(d.name))
						.text(d.name)
				)
				.append($('<span class="text-muted">').text(" · " + d.external_id))
				.appendTo(content)
		);
		if (r.message.can_manage)
			dialog.set_primary_action(__("Update production"), async () => {
				await update(s.name);
				dialog.hide();
				details(s.name);
			});
		dialog.set_secondary_action_label(__("Open station record"));
		dialog.set_secondary_action(() => frappe.set_route("Form", "Solar Station", s.name));
		dialog.show();
	}
	async function load() {
		clearTimeout(timer);
		const current = ++generation;
		const r = await call(
			"get_overview",
			{
				provider: provider.get_value() || "Deye",
				account: account.get_value() || null,
				search: search.get_value() || null,
				start: offset,
			},
			"GET"
		);
		if (current !== generation) return;
		const data = r.message;
		body.children(":not(style)").remove();
		page.clear_primary_action();
		page.clear_secondary_action();
		if (provider.get_value() !== "Deye") {
			body.append($("<p>").text(__("Integration planned.")));
			return;
		}
		account.df.options = [
			{ label: __("All accounts"), value: "" },
			...data.accounts.map((a) => ({
				label: a.company_name ? `${a.account_label} — ${a.company_name}` : a.account_label,
				value: a.name,
			})),
		];
		account.refresh();
		cards(data.summary);
		body.append(
			$('<p class="text-muted">').text(
				__(
					"{0} stations · {1} online · {2} devices · {3} stations with stale or missing readings",
					[
						data.station_count,
						data.summary.online_count,
						data.device_count,
						data.summary.stale_count,
					]
				)
			)
		);
		if (data.can_manage) {
			page.set_primary_action(__("Update production"), async () => {
				const res = await call("refresh_production", {
					account: account.get_value() || null,
				});
				frappe.show_alert({
					message: __("Queued: {0}, running: {1}, cached: {2}", [
						res.message.Queued,
						res.message.Running,
						res.message.Cached,
					]),
					indicator: "blue",
				});
				load();
			});
			page.set_secondary_action(__("Fetch Stations & Devices"), async () => {
				if (!account.get_value()) {
					frappe.msgprint(__("Select an account first."));
					return;
				}
				await call("sync_inventory", { account: account.get_value() });
				load();
			});
		}
		data.accounts
			.filter((a) => !account.get_value() || a.name === account.get_value())
			.forEach((a) => {
				if (["Queued", "Running", "Failed"].includes(a.sync_status))
					body.append(
						$("<p>").text(
							__("{0}: Inventory {1} {2}", [
								a.account_label,
								__(a.sync_status),
								a.sync_error || "",
							])
						)
					);
				if (a.company_lookup_error)
					body.append($('<p class="text-danger">').text(a.company_lookup_error));
			});
		body.append($('<h4 class="mt-4">').text(__("Station overview")));
		const table = $(
			`<div class="table-responsive"><table class="table table-bordered"><thead><tr>${[
				__("Station"),
				__("Connection"),
				__("Capacity (kWp)"),
				__("Power (kW)"),
				__("Today (kWh)"),
				__("Month (kWh)"),
				__("Lifetime (kWh)"),
				__("Last fetched"),
				__("Update"),
			]
				.map((h) => `<th>${esc(h)}</th>`)
				.join("")}</tr></thead><tbody></tbody></table></div>`
		).appendTo(body);
		data.stations.forEach((s) => {
			const tr = $("<tr>").appendTo(table.find("tbody"));
			$("<td>")
				.append(
					$('<button class="btn btn-link p-0 sm-station">')
						.text(s.station_name || s.name)
						.on("click", () => details(s.name))
				)
				.append($('<div class="sm-note">').text(s.location || ""))
				.appendTo(tr);
			$("<td>")
				.text(s.connection_status || __("Unknown"))
				.appendTo(tr);
			[
				"capacity_kw",
				"production_power_kw",
				"daily_production_kwh",
				"monthly_production_kwh",
				"total_production_kwh",
			].forEach((f) => $("<td>").text(format(s[f])).appendTo(tr));
			$("<td>")
				.text(fetched(s.last_production_fetch))
				.append(
					$('<div class="sm-note">').text(
						s.production_error ||
							(["Queued", "Running"].includes(s.production_status)
								? s.production_status
								: s.stale
								? __("Stale / missing")
								: "")
					)
				)
				.appendTo(tr);
			const actions = $("<td>").appendTo(tr);
			if (data.can_manage) {
				const btn = $('<button class="btn btn-default btn-sm">')
					.text(__("Update"))
					.prop("disabled", ["Queued", "Running"].includes(s.production_status))
					.appendTo(actions);
				btn.on("click", () => update(s.name, btn));
			}
		});
		if (!data.stations.length)
			body.append(
				$('<p class="text-muted">').text(
					__("No stations. Select an account and fetch stations and devices.")
				)
			);
		const controls = $('<div class="mt-3">').appendTo(body);
		$('<button class="btn btn-default mr-2">')
			.text(__("Previous"))
			.prop("disabled", offset === 0)
			.appendTo(controls)
			.on("click", () => {
				offset = Math.max(0, offset - 100);
				load();
			});
		$('<button class="btn btn-default">')
			.text(__("Next"))
			.prop("disabled", offset + 100 >= data.filtered_count)
			.appendTo(controls)
			.on("click", () => {
				offset += 100;
				load();
			});
		if (data.busy || data.accounts.some((a) => ["Queued", "Running"].includes(a.sync_status)))
			timer = setTimeout(() => {
				if ($(wrapper).is(":visible")) load();
			}, 5000);
	}
	load();
};
