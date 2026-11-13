frappe.ui.form.on("Site Visit", {
    setup(frm) {
        frm.set_query("site_visit_by", () => ({query: "wahni_solar.site_visit.api.supervisor_query"}));
    },
    async solar_proposal(frm) {
        if (!frm.is_new() || !frm.doc.solar_proposal) return;
        const proposal = frm.doc.solar_proposal;
        const {message} = await frappe.call({
            method: "wahni_solar.site_visit.api.make_site_visit",
            args: {source_name: proposal},
        });
        if (!message || frm.doc.solar_proposal !== proposal) return;
        if (!message.__islocal) {
            frappe.set_route("Form", "Site Visit", message.name);
            return;
        }
        const linked = ["lead", "customer", "company", "currency", "lead_owner", "lead_source"];
        const editable = ["customer_name", "requested_capacity_kw", "contact_number", "email_id",
            "consumer_number", "consumer_phone_number", "address", "location", "pincode"];
        const previous = frm._proposal_defaults || {};
        const values = {};
        for (const field of [...linked, ...editable]) {
            if (linked.includes(field) || !frm.doc[field] || frm.doc[field] === previous[field]) {
                values[field] = message[field] ?? null;
            }
        }
        frm._proposal_defaults = message;
        await frm.set_value(values);
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Solar Proposal"), () => {
            frappe.set_route("Form", "Solar Proposal", frm.doc.solar_proposal);
        }, __("View"));
    },
});
