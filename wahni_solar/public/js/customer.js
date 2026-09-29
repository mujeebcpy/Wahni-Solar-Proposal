frappe.ui.form.on('Customer', {
    refresh(frm) {
        // used by the "+" button on the Solar Proposal dashboard connection
        frm.make_methods = frm.make_methods || {};
        frm.make_methods['Solar Proposal'] = () => {
            frappe.model.open_mapped_doc({
                method: 'wahni_solar.wahni_solar_proposal.doctype.solar_proposal.solar_proposal.make_solar_proposal_from_customer',
                frm: frm
            });
        };
    }
});
