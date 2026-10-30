frappe.ui.form.on("Solar API Account", {
	refresh(frm) {
		if (frm.is_new() || !["Deye", "Enphase"].includes(frm.doc.provider) || !frm.doc.enabled)
			return;
		// frappe.msgprint parses strings starting with "{" as dialog options, so never pass raw JSON.
		const call = (method, describe, args = {}) =>
			frappe
				.call({
					method: `wahni_solar.solar_monitor.api.${method}`,
					args: { account: frm.doc.name, ...args },
					freeze: true,
				})
				.then((r) => {
					if (r.message) frappe.msgprint(describe(r.message));
					frm.reload_doc();
				});
		const connected = (r) =>
			r.status === "Connected"
				? { message: __("Connected successfully."), indicator: "green" }
				: { message: __("Connection failed: {0}", [r.error]), indicator: "red" };
		if (frm.doc.provider === "Enphase") {
			frm.add_custom_button(__("Authorize with Enphase"), () => authorize_enphase(frm, call, connected));
		}
		frm.add_custom_button(__("Test Connection"), () => call("test_connection", connected));
		if (frm.doc.provider === "Deye") {
			frm.add_custom_button(__("Fetch / Update Company Details"), () =>
				call("fetch_company_details", (r) =>
					r.company_lookup_error
						? { message: r.company_lookup_error, indicator: "red" }
						: { message: __("Company: {0}", [r.company_name]), indicator: "green" }
				)
			);
		}
		const synced = (r) => ({
			message: __(
				"Inventory sync is {0}. Stations and devices will update in the background; reload this form to see the result.",
				[r.status]
			),
			indicator: "blue",
		});
		frm.add_custom_button(__("Fetch Stations & Devices"), () => call("sync_inventory", synced));
		if (frm.doc.provider === "Enphase") {
			// Normal fetches read device lists of new systems only; this re-reads all (1 API hit per system).
			frm.add_custom_button(__("Refresh All Devices"), () =>
				frappe.confirm(
					__("Re-read the device list of every system? This uses one Enphase API hit per system."),
					() => call("sync_inventory", synced, { refresh_devices: 1 })
				)
			);
		}
	},
});

function authorize_enphase(frm, call, connected) {
	frappe
		.call({
			method: "wahni_solar.solar_monitor.api.enphase_authorize_url",
			args: { account: frm.doc.name },
		})
		.then((r) => {
			// The callback method finishes on its own and returns to this form.
			if (r.message.redirect_uri.includes("wahni_solar.solar_monitor.api.enphase_callback")) {
				window.location.href = r.message.url;
				return;
			}
			// A link click is a user gesture, so popup blockers allow it after this async call.
			const link = $("<a target='_blank' rel='noopener noreferrer' class='btn btn-default btn-sm'>")
				.attr("href", r.message.url)
				.text(__("1. Open Enphase sign-in"));
			const dialog = new frappe.ui.Dialog({
				title: __("Authorize with Enphase"),
				fields: [
					{ fieldname: "link", fieldtype: "HTML" },
					{
						fieldname: "code",
						fieldtype: "Data",
						label: __("2. Authorization Code"),
						reqd: 1,
						description: __(
							"Sign in with the Enphase installer or owner account and approve access. Paste the code shown on the Enphase page, or the whole address from the browser bar."
						),
					},
				],
				primary_action_label: __("Connect"),
				primary_action(values) {
					dialog.hide();
					call("enphase_authorize", connected, { code: values.code });
				},
			});
			dialog.fields_dict.link.$wrapper.append(link);
			dialog.show();
		});
}
