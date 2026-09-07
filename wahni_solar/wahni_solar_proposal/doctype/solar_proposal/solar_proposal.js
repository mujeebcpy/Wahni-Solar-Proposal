frappe.ui.form.on("Solar Proposal", {

    refresh(frm) {
        calculate_final(frm);
    },

    capacity_kw(frm) {

    calculate_panel_count(frm);

    if (flt(frm.doc.capacity_kw) > 0) {
        load_subsidy(frm, frm.doc.capacity_kw);
    }
},

    panel_count(frm) {

        if (!frm.doc.panel_count || flt(frm.doc.panel_count) <= 0) {
            
            frm.clear_table("table_proposal_bom");
            frm.clear_table("cost_breakdown");
            frm.refresh_field("table_proposal_bom");
            frm.refresh_field("cost_breakdown");

            calculate_final(frm);
            return;
        }
        
        load_cost_breakdown(frm);
        if (!frm.doc.package_name) {
            return;
        }

        // Get selected package
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Solar Package",
                name: frm.doc.package_name
            },
            callback: function(r) {

                if (!r.message) {
                    frappe.msgprint("Unable to load Solar Package.");
                    return;
                }

                const solar_package = r.message;

                const inverter_bom_item =
                    solar_package.inverter_bom_item;

                const basic_bom_item =
                    solar_package.basic_bom_item;

                if (!inverter_bom_item && !basic_bom_item) {
                    frappe.msgprint(
                        "No Inverter BOM Item or Basic BOM Item is configured for this Solar Package."
                    );
                    return;
                }

                const bom_items = [];

                if (inverter_bom_item) {
                    bom_items.push({
                        item_code: inverter_bom_item,
                        label: "Inverter"
                    });
                }

                if (basic_bom_item) {
                    bom_items.push({
                        item_code: basic_bom_item,
                        label: "Basic"
                    });
                }

                frm.clear_table("table_proposal_bom");

                load_bom(0);

                function load_bom(index) {

                    if (index >= bom_items.length) {

                        frm.refresh_field("table_proposal_bom");

                        frappe.show_alert({
                            message: `${frm.doc.table_proposal_bom.length} items loaded from ${bom_items.length} BOM(s)`,
                            indicator: "green"
                        });

                        calculate_final(frm);

                        return;
                    }

                    const bom_item = bom_items[index];

                    frappe.call({
                        method: "frappe.client.get_list",
                        args: {
                            doctype: "BOM",
                            filters: {
                                item: bom_item.item_code,
                                is_default: 1,
                                docstatus: 1
                            },
                            fields: ["name"],
                            limit_page_length: 1
                        },
                        callback: function(r) {

                            if (!r.message || !r.message.length) {

                                frappe.msgprint(
                                    `No default BOM found for Item: ${bom_item.item_code}`
                                );

                                load_bom(index + 1);
                                return;
                            }

                            const bom_name = r.message[0].name;

                            frappe.call({
                                method: "frappe.client.get",
                                args: {
                                    doctype: "BOM",
                                    name: bom_name
                                },
                                callback: function(r) {

                                    if (!r.message) {

                                        frappe.msgprint(
                                            `Unable to load BOM: ${bom_name}`
                                        );

                                        load_bom(index + 1);
                                        return;
                                    }

                                    const bom = r.message;

                                    (bom.items || []).forEach(function(item) {

                                        const row = frm.add_child(
                                            "table_proposal_bom"
                                        );

                                        row.item_code = item.item_code;
                                        row.quantity = item.qty;
                                        row.uom = item.uom;
                                        row.print_name = item.print_name;
                                        row.print_category = item.print_category;
                                        row.rate = item.rate;
                                        row.amount =
                                            flt(item.qty) * flt(item.rate);
                                    });

                                    load_bom(index + 1);
                                }
                            });
                        }
                    });
                }
            }
        });
    },

    package_name(frm) {

        if (!frm.doc.package_name) {
            frm.clear_table("table_proposal_bom");
            frm.refresh_field("table_proposal_bom");
            return;
        }

        if (flt(frm.doc.capacity_kw) > 0) {
            load_subsidy(frm, frm.doc.capacity_kw);
        }
    },

    discount(frm) {
        calculate_final(frm);
    },

    subsidy(frm) {
        calculate_final(frm);
    },

    other_cost(frm) {
        calculate_final(frm);
    },

    table_proposal_bom_add(frm) {
        calculate_final(frm);
    },

    table_proposal_bom_remove(frm) {
        calculate_final(frm);
    },

    table_proposal_bom_amount(frm) {
        calculate_final(frm);
    }
});


function calculate_panel_count(frm) {

    if (!frm.doc.capacity_kw) {
        frm.set_value("panel_count", 0);
        return;
    }

    frappe.db.get_doc(
        "Wahni Default Settings",
        "Wahni Default Settings"
    ).then(settings => {

        const panel_min_capacity =
            flt(settings.panel_min_capacity);

        const capacity_kw =
            flt(frm.doc.capacity_kw);

        if (!panel_min_capacity) {
            frappe.msgprint(
                "Panel Min Capacity is not configured in Wahni Default Settings."
            );
            return;
        }

        const panel_count =
            Math.ceil(
                (capacity_kw * 1000) / panel_min_capacity
            );

        frm.set_value(
            "panel_count",
            panel_count
        );
    });
}


function load_subsidy(frm, capacity) {

    frappe.db.get_doc(
        "Wahni Default Settings",
        "Wahni Default Settings"
    ).then(settings => {

        const rules =
            settings.table_subsidy_rule || [];

        const rule = rules.find(row =>
            flt(row.capacity_from) <= flt(capacity) &&
            flt(row.capacity_to) >= flt(capacity)
        );

        frm.set_value(
            "subsidy",
            rule ? flt(rule.subsidy_amount) : 0
        );

        calculate_final(frm);
    });
}


function calculate_final(frm) {

    let material_cost = 0;

    (frm.doc.table_proposal_bom || []).forEach(row => {

        const quantity = flt(row.quantity);
        const rate = flt(row.rate);

        const amount = quantity * rate;

        row.amount = amount;

        material_cost += amount;
    });

    frm.set_value(
        "material_cost",
        material_cost
    );

    const other_cost =
        flt(frm.doc.other_cost);

    const discount =
        flt(frm.doc.discount);

    const subsidy =
        flt(frm.doc.subsidy);

    const project_cost =
        material_cost + other_cost;

    frm.set_value(
        "project_cost",
        project_cost
    );

    const final_amount =
        project_cost - discount - subsidy;

    frm.set_value(
        "final_amount",
        final_amount
    );

    frm.refresh_field(
        "table_proposal_bom"
    );
}


function load_cost_breakdown(frm) {
    frappe.db.get_doc(
        "Wahni Default Settings",
        "Wahni Default Settings"
    ).then(settings => {

        const template = settings.table_cost_calculation || [];

        frm.clear_table("cost_breakdown");

        template.forEach(template_row => {
            const row = frm.add_child("cost_breakdown");

            row.cost_component = template_row.cost_component;
            row.rate = flt(template_row.rate);

            apply_cost_calculation(
                row,
                template_row.cost_component,
                settings,
                frm
            );
        });

        calculate_cost_breakdown(frm, settings);
    });
}

function apply_cost_calculation(row, component, settings, frm) {
    const capacity_kw = flt(frm.doc.capacity_kw);
    const panel_count = flt(frm.doc.panel_count);
    const panel_capacity = flt(settings.panel_max_cacpacity);

    if (component === "Panel Cost") {
        row.quantity = panel_count;
        row.included = 1;
        row.calculation_note = `${panel_count} panels × ${panel_capacity}W`;
    }

    else if (component === "Structure Material") {
        row.quantity = Math.ceil(panel_count / 2);
        row.included = 1;
        row.calculation_note = `${capacity_kw} kW`;
    }

    else if (component === "Labour Structural") {
        row.quantity = Math.ceil(panel_count / 2);
        row.included = 1;
        row.calculation_note = `${panel_count} ÷ 2`;
    }

    else if (component === "Labour Electrical") {
        row.quantity = Math.ceil(panel_count / 2);
        row.included = 1;
        row.calculation_note = `${panel_count} panels ÷ 2`;
    }

    else if (component === "Supervisor Documentation and Visits") {
        row.quantity = 1;
        row.included = 1;
        row.calculation_note = "1 × Supervisor";
    }

    else if (component === "Sales Commission") {
        row.quantity = capacity_kw;
        row.included = 1;
        row.calculation_note = `${capacity_kw} kW`;
    }

    else if (component === "Shipping") {
        row.quantity = 1;
        row.included = 1;
        row.calculation_note = "1 × Shipping";
    }

    else if (component === "Margin") {
        row.quantity = 1;
        row.included = 1;
        row.calculation_note = "1 × Margin";
    }

    else if (component === "Walk Way") {
        row.quantity = 0;
        row.included = 0;
        row.calculation_note = "Optional";
    }

    else if (component === "Ladder") {
        row.quantity = 0;
        row.included = 0;
        row.calculation_note = "Optional";
    }
}

function calculate_cost_breakdown(frm) {
    frappe.db.get_doc(
        "Wahni Default Settings",
        "Wahni Default Settings"
    ).then(settings => {

        const panel_capacity = flt(settings.panel_max_cacpacity);
        let total = 0;

        (frm.doc.cost_breakdown || []).forEach(row => {
            const rate = flt(row.rate);
            const quantity = flt(row.quantity);

            if (row.cost_component === "Panel Cost") {
                row.amount = row.included
                    ? rate * panel_capacity * quantity
                    : 0;
            } else {
                row.amount = row.included
                    ? rate * quantity
                    : 0;
            }

            total += flt(row.amount);
        });

        frm.refresh_field("cost_breakdown");
        frm.set_value("other_cost", total);

        calculate_final(frm);
    });
}


// auto calculate amount
frappe.ui.form.on("Project Cost Breakdown", {

    rate(frm, cdt, cdn) {
        calculate_cost_breakdown(frm);
    },

    quantity(frm, cdt, cdn) {
        calculate_cost_breakdown(frm);
    },

    included(frm, cdt, cdn) {
        calculate_cost_breakdown(frm);
    }

});