frappe.ui.form.on("Solar Proposal", {
    setup(frm) {
        frm.set_query("proposal_to", () => ({filters: {name: ["in", ["Customer", "Lead", "Prospect"]]}}));
        frm.set_query("package_name", () => ({filters: {disabled: 0}}));
        frm.set_query("valuation_warehouse", () => ({filters: {company: frm.doc.company, is_group: 0, disabled: 0}}));
        frm._preview_debounced = frappe.utils.debounce(() => preview(frm), 350);
    },
    refresh(frm) {
        frm.set_df_property("party", "label", __(frm.doc.proposal_to || "Party"));
        frm.set_df_property("input_values", "hidden", 1);
        render_inputs(frm);
        if (frm.is_new() && !frm.doc.calculation_version) frm.doc.calculation_version = "Templates v1";
        if (frm.doc.calculation_version === "Templates v1") {
            const grid = frm.fields_dict.table_proposal_bom.grid;
            grid.cannot_add_rows = true;
            grid.cannot_delete_rows = true;
            ["item_code", "uom"].forEach(field => grid.update_docfield_property(field, "read_only", 1));
            grid.refresh();
        }
        if (!frm.is_new()) {
            frm.add_custom_button(__("Regenerate Materials"), () => {
                frappe.confirm(__("Reload current templates and reset direct material quantity overrides? Site input values will be kept."),
                    () => run_document_action(frm, "regenerate_materials"));
            }, __("Configuration"));
            if (frm.doc.calculation_version === "Templates v1") {
                frm.add_custom_button(__("Refresh Valuation"), () => run_document_action(frm, "refresh_valuation"), __("Configuration"));
            }
            frm.add_custom_button(__("Project"), () => frappe.model.open_mapped_doc({
                method: "wahni_solar.wahni_solar_proposal.doctype.solar_proposal.solar_proposal.make_project", frm
            }), __("Create"));
        }
        frm.add_custom_button(__("Calculate Materials"), () => preview(frm, true));
        frm.add_custom_button(__("Use Suggested Panel Count"), () => {
            if (frm.doc.suggested_panel_count) frm.set_value("panel_count", frm.doc.suggested_panel_count);
        }, __("Configuration"));
    },
    proposal_to(frm) {
        frm.set_df_property("party", "label", __(frm.doc.proposal_to || "Party"));
        frm.set_value("party", "");
    },
    async party(frm) {
        if (!frm.doc.party) return frm.set_value("customer_name", "");
        const type = frm.doc.proposal_to;
        if (type === "Customer") {
            const r = await frappe.db.get_value(type, frm.doc.party, "customer_name");
            frm.set_value("customer_name", r.message.customer_name);
        } else if (type === "Lead") {
            const r = await frappe.db.get_value(type, frm.doc.party, ["lead_name", "company_name"]);
            frm.set_value("customer_name", r.message.company_name || r.message.lead_name);
        } else frm.set_value("customer_name", frm.doc.party);
    },
    async package_name(frm) {
        if (frm._applying_calculation) return;
        frm._preview_sequence = (frm._preview_sequence || 0) + 1;
        frm._refresh_subsidy = true;
        if (!frm.doc.package_name) return;
        const package_name = frm.doc.package_name;
        frm.clear_table("table_proposal_bom");
        frm.refresh_field("table_proposal_bom");
        const r = await frappe.call({
            method: "wahni_solar.wahni_solar_proposal.api.package_inputs",
            args: {package_name, supplied: frm.doc.input_values || []}
        });
        if (package_name !== frm.doc.package_name) return;
        frm.clear_table("input_values");
        (r.message || []).forEach(values => Object.assign(frm.add_child("input_values"), values));
        render_inputs(frm);
        schedule(frm);
    },
    capacity_kw(frm) { count_input_changed(frm); frm._refresh_subsidy = true; schedule(frm); },
    panel_capacity_w(frm) { count_input_changed(frm); schedule(frm); },
    panel_count(frm) { frm._auto_panel_count = null; schedule(frm); },
    connection_type: schedule,
    down_run_cabling: schedule,
    include_battery: schedule,
    include_structure: schedule,
    company: schedule,
    valuation_warehouse: schedule,
    discount: schedule,
    subsidy: schedule,
    async validate(frm) {
        if (frm.doc.calculation_version !== "Legacy") await preview(frm, true);
    }
});

function schedule(frm) {
    if (!frm._applying_calculation && frm.doc.calculation_version !== "Legacy") {
        frm._preview_sequence = (frm._preview_sequence || 0) + 1;
        frm._preview_debounced();
    }
}

function count_input_changed(frm) {
    if (frm._applying_calculation) return;
    // Only advance an untouched suggestion; a staff-selected count is authoritative.
    if (!frm.doc.panel_count || frm.doc.panel_count === frm.doc.suggested_panel_count || frm.doc.panel_count === frm._auto_panel_count) {
        const watts = flt(frm.doc.panel_capacity_w);
        if (watts > 0 && flt(frm.doc.capacity_kw) > 0) {
            frm.doc.panel_count = Math.ceil(flt(frm.doc.capacity_kw) * 1000 / watts);
            frm._auto_panel_count = frm.doc.panel_count;
            frm.refresh_field("panel_count");
        }
    }
}

async function preview(frm, required = false) {
    if (frm._applying_calculation || frm.doc.calculation_version === "Legacy") return;
    if (!frm.doc.package_name || !flt(frm.doc.capacity_kw) || !flt(frm.doc.panel_capacity_w)) {
        if (required) frappe.throw(__("Select a system and enter positive system and panel capacities."));
        return;
    }
    if (!required && (frm.doc.input_values || []).some(row => row.required && !row.show_when && (row.value === "" || row.value == null))) return;
    const sequence = frm._preview_sequence = (frm._preview_sequence || 0) + 1;
    const refresh_subsidy = !!frm._refresh_subsidy;
    const r = await frappe.call({
        method: "wahni_solar.wahni_solar_proposal.api.preview_proposal",
        args: {doc: frm.doc, refresh_subsidy}
    });
    if (sequence !== frm._preview_sequence || !r.message) return;
    frm._applying_calculation = true;
    try {
        for (const [key, value] of Object.entries(r.message)) {
            if (["input_values", "table_proposal_bom", "cost_breakdown"].includes(key)) {
                frm.clear_table(key);
                (value || []).forEach(values => {
                    const row = frm.add_child(key);
                    for (const [field, entry] of Object.entries(values)) {
                        if (!["name", "parent", "parentfield", "parenttype", "idx", "doctype", "owner", "creation", "modified", "modified_by", "docstatus"].includes(field)) row[field] = entry;
                    }
                });
                frm.refresh_field(key);
            } else {
                frm.doc[key] = value;
                frm.refresh_field(key);
            }
        }
        frm._refresh_subsidy = false;
        frm._auto_panel_count = frm.doc.panel_count === frm.doc.suggested_panel_count ? frm.doc.panel_count : null;
        frm.dirty();
        render_inputs(frm);
    } finally {
        frm._applying_calculation = false;
    }
}

async function run_document_action(frm, method) {
    if (frm.is_dirty()) await frm.save();
    await frm.call(method);
    await frm.reload_doc();
}

function render_inputs(frm) {
    const wrapper = frm.fields_dict.input_editor.$wrapper;
    wrapper.empty();
    if (!(frm.doc.input_values || []).length) return;
    $("<h5>").text(__("Additional Site Inputs")).appendTo(wrapper);
    const container = $("<div class='row'>").appendTo(wrapper);
    (frm.doc.input_values || []).forEach(row => {
        const column = $("<div class='col-sm-6'>").appendTo(container);
        const fieldtype = ["Int", "Float", "Check", "Select", "Data"].includes(row.input_type) ? row.input_type : "Data";
        let control;
        let initializing = true;
        control = frappe.ui.form.make_control({
            parent: column,
            df: {
                fieldname: row.variable_key, fieldtype,
                label: row.label || row.variable_key,
                description: row.uom ? __("Unit: {0}", [row.uom]) : "",
                options: row.select_options || "", reqd: row.required,
                onchange() {
                    if (frm._applying_calculation || initializing || !control) return;
                    row.value = String(control.get_value() ?? "");
                    frm.dirty();
                    schedule(frm);
                }
            }, render_input: true
        });
        const initial = fieldtype === "Check" ? cint(row.value) : row.value;
        Promise.resolve(control.set_value(initial)).finally(() => { initializing = false; });
        if (row.is_visible === 0) column.hide();
    });
}

frappe.ui.form.on("Solar Proposal BOM Item", {
    quantity(frm, cdt, cdn) {
        if (frm._applying_calculation || frm.doc.calculation_version === "Legacy") return;
        const row = locals[cdt][cdn];
        frm._preview_sequence = (frm._preview_sequence || 0) + 1;
        row.has_quantity_override = 1;
        frm.dirty();
        if (!row.override_reason) {
            frappe.prompt({fieldname: "reason", fieldtype: "Small Text", label: __("Reason for quantity change"), reqd: 1},
                values => { row.override_reason = values.reason; schedule(frm); }, __("Site quantity override"));
        } else schedule(frm);
    },
    override_reason: schedule
});

frappe.ui.form.on("Project Cost Breakdown", {
    rate: schedule, quantity: schedule, included: schedule,
    cost_breakdown_remove: schedule
});
