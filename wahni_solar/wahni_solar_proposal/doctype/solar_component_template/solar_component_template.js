// Copyright (c) 2026, mujeebcpy and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Component Template", {
    setup(frm) {
        frm.set_query("item_code", "items", () => ({ filters: { disabled: 0, has_variants: 0 } }));
    },

    refresh(frm) {
        const load = callback => frappe.require("/assets/wahni_solar/js/solar_rule_editor.js", callback);
        frm.add_custom_button(__("Rule Reference"), () => load(() =>
            wahni_solar.solar_rule_editor.reference(null, frm.doc.items || [])
        ), __("Rule Helpers"));
        if (frm.perm[0]?.write) {
            frm.add_custom_button(__("Build Condition"), () => load(() =>
                wahni_solar.solar_rule_editor.condition_builder(frm, "items", "rule_key")
            ), __("Rule Helpers"));
            frm.add_custom_button(__("Quantity Formula"), () => load(() =>
                wahni_solar.solar_rule_editor.quantity_helper(frm)
            ), __("Rule Helpers"));
        }
        frm.add_custom_button(__("Test Rules"), () => {
            if (frm.is_new() || frm.is_dirty()) {
                return frappe.msgprint(__("Save the template before testing its rules."));
            }
            load(() => wahni_solar.solar_rule_editor.test_template(frm));
        });
    }
});
