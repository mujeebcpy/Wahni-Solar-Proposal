frappe.ui.form.on("Project Report", {
    refresh(frm) {
        const downloads = frm.doc.__onload?.downloads || {};
        const labels = { pdf: __("Project Report PDF"), qet: __("Editable SLD Drawing") };
        for (const [output, url] of Object.entries(downloads)) {
            frm.add_custom_button(labels[output] || output, () => window.open(url), __("Download"));
        }
        if (!frm.is_new() && !Object.keys(downloads).length && !["Queued", "Running"].includes(frm.doc.status)) {
            frm.set_intro(__("Generated files are not stored. Generate the report again from the Project to download it."), "blue");
        }
    },
});
