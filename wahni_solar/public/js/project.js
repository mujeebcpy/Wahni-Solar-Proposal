(() => {
    const api = "wahni_solar.solar_project.api";
    const DOCUMENTS = ["Customer Vendor Agreement", "KSEB Agreement", "Check List", "Project Completion Report"];
    const escape = (value) => frappe.utils.escape_html(String(value || ""));

    function update_grid_connection(frm) {
        if (!frm.dashboard.transactions_area || !frm.__report_grid_choices) return;
        // The report can resolve Grid Checks through Customer -> Lead even when
        // the optional explicit Grid Check field on Project has not been selected.
        const names = frm.doc.custom_report_grid_check
            ? [frm.doc.custom_report_grid_check] : frm.__report_grid_choices;
        const doctype = "KSEB Grid Check";
        const links = (frm.dashboard.internal_links_found || []).filter((link) => link.doctype !== doctype);
        links.push({ doctype, names, count: names.length, open_count: 0 });
        frm.dashboard.internal_links_found = links;
        frm.dashboard.set_badge_count_for_internal_link(doctype, 0, names.length, names);
        const link = frm.dashboard.transactions_area.find('.document-link[data-doctype="KSEB Grid Check"]');
        link.attr("data-names", names.join(","));
        link.find(".count").toggleClass("hidden", !names.length).text(names.length);
        if (names.length) link.find("a").removeAttr("disabled");
    }

    function show_result(frm, report) {
        let result = {};
        try { result = JSON.parse(report.result || "{}"); } catch (_) { /* Empty while queued. */ }
        const downloads = report.downloads || {};
        const links = [
            ["Project Report PDF", downloads.pdf],
            ["Editable SLD Drawing", downloads.qet],
        ].filter(([, url]) => url).map(([label, url]) =>
            `<li><a href="${escape(url)}" target="_blank" rel="noopener">${__(label)}</a></li>`
        ).join("");
        const omissions = (result.omitted || []).map((row) =>
            `<li>${escape(row.category)}: ${escape(row.reason)}</li>`
        ).join("");
        const warnings = (result.warnings || []).map((value) => `<li>${escape(value)}</li>`).join("");
        const blanks = Object.entries(result.missing_fields || {}).map(([category, fields]) => {
            const edit = DOCUMENTS.includes(category)
                ? ` <a href="#" data-edit-document="${escape(category)}">${__("Edit details")}</a>` : "";
            return `<li>${escape(category)}: ${fields.length} ${__("fields left blank")}${edit}</li>`;
        }).join("");
        const dialog = frappe.msgprint({
            title: __(report.status),
            indicator: report.status === "Failed" ? "red" : report.status === "Completed" ? "green" : "orange",
            message: `<p>${escape(report.message)}</p><ul>${links}</ul>` +
                (omissions ? `<h5>${__("Documents omitted")}</h5><ul>${omissions}</ul>` : "") +
                (warnings || blanks ? `<h5>${__("Missing information")}</h5><ul>${warnings}${blanks}</ul>` : "") +
                `<p><a href="/app/project-report/${encodeURIComponent(report.name)}">${__("Open generation details")}</a></p>`,
        });
        dialog.$wrapper.find("[data-edit-document]").on("click", (event) => {
            event.preventDefault();
            dialog.hide();
            open_document(frm, event.currentTarget.dataset.editDocument);
        });
    }

    // The record is created only when a user chooses to edit its details.
    async function open_document(frm, category) {
        const { message } = await frappe.call({
            method: "wahni_solar.solar_project.project_documents.open_project_document",
            args: { project: frm.doc.name, category }, freeze: true,
        });
        if (message) frappe.set_route("Form", message.doctype, message.name);
    }

    // Generated documents are returned to the browser only; nothing is attached to Project.
    function download_url(message) {
        const bytes = Uint8Array.from(atob(message.content), (char) => char.charCodeAt(0));
        return URL.createObjectURL(new Blob([bytes], { type: message.content_type }));
    }

    frappe.ui.form.on("Project", {
        dashboard_update(frm) {
            update_grid_connection(frm);
        },
        setup(frm) {
            frm.set_query("custom_panel_item", () => ({
                filters: { item_group: "Panel" },
            }));
            frm.set_query("custom_report_sales_invoice", () => ({ filters: {
                project: frm.doc.name, customer: frm.doc.customer, docstatus: 1, is_return: 0,
            } }));
            frm.set_query("custom_report_grid_check", () => ({
                filters: { name: ["in", frm.__report_grid_choices || []] },
            }));
        },
        async refresh(frm) {
            // "+" on the Sales Order connection maps the material list server side
            frm.make_methods = frm.make_methods || {};
            frm.make_methods["Sales Order"] = () => frappe.model.open_mapped_doc({
                method: "wahni_solar.solar_project.sales_order.make_sales_order",
                frm,
            });
            if (frm.is_new()) return;
            if (frm.perm[0]?.write) {
                // One menu: each document downloads directly; its dialog offers editing details.
                for (const category of ["SLD", ...DOCUMENTS]) {
                    frm.add_custom_button(__(category), async () => {
                        if (frm.__generating) return;
                        frm.__generating = true;
                        try {
                            if (frm.is_dirty()) await frm.save();
                            const { message } = await frappe.call({
                                method: `${api}.generate_project_document`,
                                args: { project: frm.doc.name, category },
                                freeze: true, freeze_message: __("Generating {0}...", [__(category)]),
                            });
                            if (!message) return;
                            const url = download_url(message);
                            const warnings = (message.warnings || []).map((value) =>
                                `<li>${escape(value)}</li>`).join("");
                            const blanks = message.missing_fields?.length
                                ? `<p>${__("{0} fields left blank; complete them in {1}.", [message.missing_fields.length, category === "SLD" ? "QElectroTech" : __("the document details or its linked source records")])}</p>` : "";
                            const editable = DOCUMENTS.includes(category);
                            frappe.msgprint({
                                title: __(category),
                                message: `<p><a href="${url}" download="${escape(message.filename)}">${__("Download {0}", [__(category)])}</a></p>` +
                                    blanks + (warnings ? `<ul>${warnings}</ul>` : ""),
                                primary_action: editable ? {
                                    label: __("Edit Details"),
                                    action: () => { frappe.hide_msgprint(); open_document(frm, category); },
                                } : undefined,
                            });
                        } finally { frm.__generating = false; }
                    }, __("Generate"));
                }
                frm.add_custom_button(__("Project Report"), async () => {
                    if (frm.__generating) return;
                    frm.__generating = true;
                    try {
                        if (frm.is_dirty()) await frm.save();
                        const { message } = await frappe.call({
                            method: `${api}.generate_project_report`, args: { project: frm.doc.name },
                            freeze: true, freeze_message: __("Generating Project Report. This can take a minute..."),
                        });
                        if (!message) return;
                        await frm.reload_doc();
                        show_result(frm, message);
                    } finally { frm.__generating = false; }
                }, __("Generate"));
            }
            frm.add_custom_button(__("Shared Report Documents"), () => frappe.set_route("List", "Project Report Document"), __("View"));
            frm.add_custom_button(__("Report History"), () => frappe.set_route("List", "Project Report", { project: frm.doc.name }), __("View"));
            frappe.call({ method: `${api}.get_project_report_context`, args: { project: frm.doc.name },
                callback: ({ message }) => {
                    frm.__report_grid_choices = message?.grid_choices || [];
                    update_grid_connection(frm);
                },
            });
        },
    });

})();
