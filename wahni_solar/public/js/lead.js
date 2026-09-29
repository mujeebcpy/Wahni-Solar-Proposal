frappe.ui.form.on('Lead', {
    refresh(frm) {
        const make_solar_proposal = () => {
            frappe.model.open_mapped_doc({
                method: 'wahni_solar.wahni_solar_proposal.doctype.solar_proposal.solar_proposal.make_solar_proposal',
                frm: frm
            });
        };

        // used by the "+" button on the Solar Proposal dashboard connection
        frm.make_methods = frm.make_methods || {};
        frm.make_methods['Solar Proposal'] = make_solar_proposal;

        if (frm.doc.__islocal) return;

        frm.add_custom_button(__('Solar Proposal'), make_solar_proposal, __('Create'));
    }
});
