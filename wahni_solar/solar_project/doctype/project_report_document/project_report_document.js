(() => {
    const panel_category = "Panel Datasheet and BIS";
    const legacy_categories = ["Panel Datasheet", "Panel BIS"];

    function update_document_fields(frm) {
        // Keep a saved legacy value visible without offering it for new uploads.
        const options = frm.fields_dict.category.df.options.split("\n")
            .filter((category) => !legacy_categories.includes(category));
        if (!frm.is_new() && legacy_categories.includes(frm.doc.category)) {
            options.push(frm.doc.category);
        }
        frm.set_df_property("category", "options", options.join("\n"));

        const panel = frm.doc.category === panel_category;
        frm.set_df_property("brand", "label", panel ? __("Panel Brand") : __("Equipment Brand"));
        frm.set_df_property("brand", "description", panel
            ? __("Enter the panel manufacturer exactly as selected on the linked Solar Proposal, e.g. Adani or Premier.")
            : __("Leave blank for a common document, or enter the equipment brand, e.g. Enphase or Vsole."));
        frm.set_df_property("file", "label", panel ? __("Panel Datasheet and BIS PDF") : __("Document"));
        frm.set_df_property("file", "description", panel
            ? __("Attach one PDF containing both the datasheet and BIS for this brand and Wp. Leave both page numbers at zero to include the entire PDF.")
            : __("Upload the document for the selected category."));
    }

    frappe.ui.form.on("Project Report Document", {
        refresh: update_document_fields,
        category: update_document_fields,
    });
})();
