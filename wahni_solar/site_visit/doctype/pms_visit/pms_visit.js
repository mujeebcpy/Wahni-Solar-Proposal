frappe.ui.form.on("PMS Visit", {
    setup(frm) {
        frm.set_query("project", () => ({filters: {status: "Completed"}}));
        frm.set_query("service_person", () => ({query: "wahni_solar.site_visit.api.supervisor_query"}));
    },
    async project(frm) {
        if (!frm.doc.project) return;
        const project = frm.doc.project;
        const {message} = await frappe.call({
            method: "wahni_solar.site_visit.doctype.pms_visit.pms_visit.get_project_values",
            args: {project},
        });
        if (message && frm.doc.project === project) await frm.set_value(message);
    },
});
