frappe.ui.form.on("Sales Order", {

    project(frm) {

        if (frm.doc.docstatus !== 0) {
            return;
        }

        if (!frm.doc.project) {
            return;
        }

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Project",
                name: frm.doc.project
            },
            callback: function(r) {

                if (!r.message) {
                    return;
                }

                const bom_items = r.message.custom_table_project_bom || [];

                if (!bom_items.length) {
                    return;
                }

                load_items_from_bom(frm, bom_items);
            }
        });
    }
});

async function load_items_from_bom(frm, bom_items) {

    frm.clear_table("items");
    frm.refresh_field("items");

    const failed = [];

    for (const bom_item of bom_items) {

        const row = frm.add_child("items");

        try {
            // item_code trigger fetches item defaults (rate, uom, description)
            // so it must resolve before we override with the BOM's own values
            await frappe.model.set_value(row.doctype, row.name, "item_code", bom_item.item_code);

            if (bom_item.uom) {
                await frappe.model.set_value(row.doctype, row.name, "uom", bom_item.uom);
            }

            await frappe.model.set_value(row.doctype, row.name, "qty", bom_item.quantity);
            await frappe.model.set_value(row.doctype, row.name, "rate", bom_item.rate);
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
