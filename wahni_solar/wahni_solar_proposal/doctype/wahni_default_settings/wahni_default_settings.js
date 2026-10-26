frappe.ui.form.on("Wahni Default Settings", {
    setup(frm) {
        frm.set_query("valuation_warehouse", () => ({filters: {company: frm.doc.costing_company, is_group: 0, disabled: 0}}));
    },
    refresh(frm) {
        if (!frappe.user.has_role("System Manager")) return;
        frm.add_custom_button(__("Install Demo Defaults"), async () => {
            const r = await frappe.call({method: "wahni_solar.wahni_solar_proposal.api.install_demo_defaults", freeze: true});
            show_demo_report(r.message);
            frm.reload_doc();
        }, __("Demo"));
        frm.add_custom_button(__("Clear Demo Defaults"), () => {
            frappe.confirm(__("Remove tagged demo proposals, packages and templates? Linked records, uploads and actual Items are preserved."), async () => {
                const r = await frappe.call({method: "wahni_solar.wahni_solar_proposal.demo.clear_demo_configuration", freeze: true});
                show_demo_report(r.message);
                frm.reload_doc();
            });
        }, __("Demo"));
    }
});

function show_demo_report(report) {
    const escape = frappe.utils.escape_html;
    frappe.msgprint({title: __("Demo configuration"), message: `<pre>${escape(JSON.stringify(report || {}, null, 2))}</pre>`});
}
