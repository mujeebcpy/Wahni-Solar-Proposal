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

    for (const bom_item of bom_items) {

        const row = frm.add_child("items");

        // item_code trigger fetches item defaults (rate, uom, description)
        // so it must resolve before we override with the BOM's own values
        await frappe.model.set_value(row.doctype, row.name, "item_code", bom_item.item_code);

        if (bom_item.uom) {
            await frappe.model.set_value(row.doctype, row.name, "uom", bom_item.uom);
        }

        await frappe.model.set_value(row.doctype, row.name, "qty", bom_item.quantity);
        await frappe.model.set_value(row.doctype, row.name, "rate", bom_item.rate);
    }

    frm.refresh_field("items");

    if (frm.cscript && frm.cscript.calculate_taxes_and_totals) {
        frm.cscript.calculate_taxes_and_totals();
    }

    frappe.show_alert({
        message: `${frm.doc.items.length} item(s) loaded from Project Material List`,
        indicator: "green"
    });
}
