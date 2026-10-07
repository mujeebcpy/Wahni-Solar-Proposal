frappe.ui.form.on("Solar API Account", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.provider !== "Deye" || !frm.doc.enabled) return;
		const call = (method) =>
			frappe
				.call({
					method: `wahni_solar.solar_monitor.api.${method}`,
					args: { account: frm.doc.name },
					freeze: true,
				})
				.then((r) => {
					if (r.message) frappe.msgprint(JSON.stringify(r.message));
					frm.reload_doc();
				});
		frm.add_custom_button(__("Test Connection"), () => call("test_connection"));
		frm.add_custom_button(__("Fetch / Update Company Details"), () =>
			call("fetch_company_details")
		);
		frm.add_custom_button(__("Fetch Stations & Devices"), () => call("sync_inventory"));
	},
});
