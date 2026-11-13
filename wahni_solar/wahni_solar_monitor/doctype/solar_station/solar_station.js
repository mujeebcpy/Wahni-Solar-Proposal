frappe.ui.form.on("Solar Station", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.present && frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Update Production"), () =>
				frappe
					.call({
						method: "wahni_solar.solar_monitor.api.refresh_station",
						args: { station: frm.doc.name },
					})
					.then((r) => {
						frappe.show_alert({
							message: __("Production update: {0}", [r.message.status]),
							indicator: "blue",
						});
						frm.reload_doc();
					})
			);
		}
	},
});
