frappe.ui.form.on('Lead', {
    refresh(frm) {
        if (frm.doc.__islocal) return;

        frm.add_custom_button(__('Solar Proposal'), () => {
            frappe.model.open_mapped_doc({
                method: 'wahni_solar.wahni_solar_proposal.doctype.solar_proposal.solar_proposal.make_solar_proposal',
                frm: frm
            });
        }, __('Create'));
    }
});