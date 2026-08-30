// Copyright (c) 2026, mujeebcpy and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Package", {
    setup(frm) {
        frm.set_query("default_bom_item", function () {
            return {
                filters: {
                    item_group: "BOM Group"
                }
            };
        });
    }
});