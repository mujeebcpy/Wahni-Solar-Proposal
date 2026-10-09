frappe.ui.form.on("Solar API Account", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.provider !== "Deye" || !frm.doc.enabled) return;
		// frappe.msgprint parses strings starting with "{" as dialog options, so never pass raw JSON.
		const call = (method, describe) =>
			frappe
				.call({
					method: `wahni_solar.solar_monitor.api.${method}`,
					args: { account: frm.doc.name },
					freeze: true,
				})
				.then((r) => {
					if (r.message) frappe.msgprint(describe(r.message));
					frm.reload_doc();
				});
		frm.add_custom_button(__("Test Connection"), () =>
			call("test_connection", (r) =>
				r.status === "Connected"
					? { message: __("Connected successfully."), indicator: "green" }
					: { message: __("Connection failed: {0}", [r.error]), indicator: "red" }
			)
		);
		frm.add_custom_button(__("Fetch / Update Company Details"), () =>
			call("fetch_company_details", (r) =>
				r.company_lookup_error
					? { message: r.company_lookup_error, indicator: "red" }
					: { message: __("Company: {0}", [r.company_name]), indicator: "green" }
			)
		);
		frm.add_custom_button(__("Fetch Stations & Devices"), () =>
			call("sync_inventory", (r) => ({
				message: __(
					"Inventory sync is {0}. Stations and devices will update in the background; reload this form to see the result.",
					[r.status]
				),
				indicator: "blue",
			}))
		);
	},
});
