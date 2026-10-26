// Copyright (c) 2026, mujeebcpy and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Package", {
    setup(frm) {
        frm.set_query("component_template", "component_rules", () => ({ filters: { disabled: 0 } }));
    },

    refresh(frm) {
        const load = callback => frappe.require("/assets/wahni_solar/js/solar_rule_editor.js", callback);
        frm.add_custom_button(__("Rule Reference"), () => load(() =>
            wahni_solar.solar_rule_editor.reference(frm.doc, frm.doc.component_rules || [])
        ), __("Rule Helpers"));
        if (frm.perm[0]?.write) {
            frm.add_custom_button(__("Build Condition"), () => load(() =>
                wahni_solar.solar_rule_editor.condition_builder(frm, "component_rules", "template_alias")
            ), __("Rule Helpers"));
        }
        frm.add_custom_button(__("Test Rules"), () => {
            if (frm.is_new() || frm.is_dirty()) {
                return frappe.msgprint(__("Save the package before testing its rules."));
            }
            load(() => wahni_solar.solar_rule_editor.preview(frm.doc));
        });
    }
});
