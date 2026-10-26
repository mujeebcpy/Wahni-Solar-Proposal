frappe.ui.form.on("Sales Order", {

    project(frm) {

        if (frm.doc.docstatus !== 0) {
            return;
        }

        if (!frm.doc.project) {
            return;
        }

        const project_name = frm.doc.project;
        frappe.call({
            method: "wahni_solar.solar_project.sales_order.get_project_materials",
            args: {
                source_name: project_name
            },
            callback: function(r) {

                if (!r.message || frm.doc.project !== project_name || frm.doc.docstatus !== 0) {
                    return;
                }

                const bom_items = r.message.items || [];

                if (!bom_items.length) {
                    return;
                }

                load_items_from_bom(frm, bom_items, r.message.use_selling_prices);
            }
        });
    }
});

async function load_items_from_bom(frm, bom_items, use_selling_prices) {

    frm.clear_table("items");
    frm.refresh_field("items");

    const failed = [];

    for (const bom_item of bom_items) {

        const row = frm.add_child("items");

        try {
            // Standard Item / UOM / quantity triggers fetch selling prices.
            // Legacy material lists explicitly retain their saved rates.
            await frappe.model.set_value(row.doctype, row.name, "item_code", bom_item.item_code);

            if (bom_item.uom) {
                await frappe.model.set_value(row.doctype, row.name, "uom", bom_item.uom);
            }

            await frappe.model.set_value(row.doctype, row.name, "qty", bom_item.quantity);
            if (!use_selling_prices) {
                await frappe.model.set_value(row.doctype, row.name, "rate", bom_item.rate);
            }
        } catch (e) {
            // one bad item (disabled, template, missing UOM conversion...) must not stop the rest
            console.error(`Could not load ${bom_item.item_code} from Project`, e);
            failed.push(bom_item.item_code);
        }
    }

    frm.refresh_field("items");

    if (frm.cscript && frm.cscript.calculate_taxes_and_totals) {
        frm.cscript.calculate_taxes_and_totals();
    }

    frappe.show_alert({
        message: `${frm.doc.items.length} item(s) loaded from Project Material List`,
        indicator: "green"
    });

    if (failed.length) {
        frappe.msgprint({
            title: __("Some items could not be loaded"),
            indicator: "orange",
            message: failed.map(item => frappe.utils.escape_html(item || __("(blank item code)"))).join("<br>")
        });
    }
}
