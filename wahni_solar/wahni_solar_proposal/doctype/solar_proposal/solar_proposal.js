// To fetch the default BOM item based on the selected package
frappe.ui.form.on("Solar Proposal", {
    package_name: function(frm) {

        if (!frm.doc.package_name) {
            frm.clear_table("table_proposal_bom");
            frm.refresh_field("table_proposal_bom");
            return;
        }

        // Get the selected Solar Package
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

                // Inverter BOM first, Basic BOM second
                const inverter_bom_item = solar_package.inverter_bom_item;
                const basic_bom_item = solar_package.basic_bom_item;

                if (!inverter_bom_item && !basic_bom_item) {
                    frappe.msgprint(
                        "No Inverter BOM Item or Basic BOM Item is configured for this Solar Package."
                    );
                    return;
                }

                // BOMs will be loaded in this order
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

                // Clear existing proposal BOM
                frm.clear_table("table_proposal_bom");

                // Function to load BOMs sequentially
                function load_bom(index) {

                    // Finished loading all BOMs
                    if (index >= bom_items.length) {

                        frm.refresh_field("table_proposal_bom");

                        frappe.show_alert({
                            message: `${frm.doc.table_proposal_bom.length} items loaded from ${bom_items.length} BOM(s)`,
                            indicator: "green"
                        });

                        return;
                    }

                    const bom_item = bom_items[index];

                    // Find the default BOM for the Item
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

                                // Continue with the next BOM
                                load_bom(index + 1);
                                return;
                            }

                            const bom_name = r.message[0].name;

                            // Get complete BOM
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

                                        // Continue with next BOM
                                        load_bom(index + 1);
                                        return;
                                    }

                                    const bom = r.message;

                                    // Append BOM items
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
                                        row.amount = item.amount;

                                    });

                                    // Load next BOM
                                    load_bom(index + 1);
                                }
                            });
                        }
                    });
                }

                // Start: Inverter BOM → Basic BOM
                load_bom(0);
            }
        });
    }
});

frappe.ui.form.on("Solar Proposal", {
    refresh(frm) {
        calculate_final(frm);
    },

    package_name(frm) {
        if (!frm.doc.package_name) {
            return;
        }

        load_subsidy(frm, frm.doc.capacity_kw);
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


function load_subsidy(frm, capacity) {

    frappe.db.get_list("Subsidy Rule", {
        filters: {
            enabled: 1,
            capacity_from: ["<=", capacity],
            capacity_to: [">=", capacity]
        },
        fields: ["subsidy_amount"],
        limit: 1
    }).then(records => {

        if (records.length > 0) {
            frm.set_value(
                "subsidy",
                records[0].subsidy_amount || 0
            );
        } else {
            frm.set_value("subsidy", 0);
        }

        calculate_final(frm);
    });
}


function calculate_final(frm) {

    let material_cost = 0;

    (frm.doc.table_proposal_bom || []).forEach(row => {

        // Calculate amount from quantity × rate
        const quantity = flt(row.quantity);
        const rate = flt(row.rate);

        const amount = quantity * rate;

        // Update row amount
        row.amount = amount;

        // Add to material cost
        material_cost += amount;
    });

    // Set Material Cost
    frm.set_value("material_cost", material_cost);

    // Other Cost
    const other_cost = flt(frm.doc.other_cost);

    // Discount
    const discount = flt(frm.doc.discount);

    // Subsidy
    const subsidy = flt(frm.doc.subsidy);

    // Project Cost
    const project_cost = material_cost + other_cost;

    frm.set_value("project_cost", project_cost);

    // Final Amount
    const final_amount = project_cost - discount - subsidy;

    frm.set_value("final_amount", final_amount);

    // Refresh child table so calculated amounts appear
    frm.refresh_field("table_proposal_bom");
}