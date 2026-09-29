(() => {
    const api = "wahni_solar.solar_project.api";
    const active = (status) => ["Queued", "Running"].includes(status);
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

    function show_result(report) {
        let result = {};
        try { result = JSON.parse(report.result || "{}"); } catch (_) { /* Empty while queued. */ }
        const links = [
            ["Project Report PDF", report.report_pdf],
            ["Editable SLD Drawing", report.sld_qet],
        ].filter(([, url]) => url).map(([label, url]) =>
            `<li><a href="${escape(url)}" target="_blank" rel="noopener">${__(label)}</a></li>`
        ).join("");
        const omissions = (result.omitted || []).map((row) =>
            `<li>${escape(row.category)}: ${escape(row.reason)}</li>`
        ).join("");
        const warnings = (result.warnings || []).map((value) => `<li>${escape(value)}</li>`).join("");
        const blanks = Object.entries(result.missing_fields || {}).map(([category, fields]) =>
            `<li>${escape(category)}: ${fields.length} ${__("fields left blank")}</li>`
        ).join("");
        frappe.msgprint({
            title: __(report.status),
            indicator: report.status === "Failed" ? "red" : report.status === "Completed" ? "green" : "orange",
            message: `<p>${escape(report.message)}</p><ul>${links}</ul>` +
                (omissions ? `<h5>${__("Documents omitted")}</h5><ul>${omissions}</ul>` : "") +
                (warnings || blanks ? `<h5>${__("Missing information")}</h5><ul>${warnings}${blanks}</ul>` : "") +
                `<p><a href="/app/project-report/${encodeURIComponent(report.name)}">${__("Open generation details")}</a></p>`,
        });
    }

    function watch(frm, name) {
        clearTimeout(frm.__report_timer);
        frm.__report_name = name;
        const poll = async () => {
            if (cur_frm !== frm || frm.__report_name !== name) return;
            try {
                const { message } = await frappe.call({ method: `${api}.get_project_report_status`, args: { report_name: name } });
                if (!message) return;
                frm.dashboard.set_headline(escape(`${message.status}: ${message.message || ""}`));
                if (active(message.status)) {
                    frm.__report_timer = setTimeout(poll, 3000);
                } else {
                    frm.__report_name = null;
                    frm.__report_completed = name;
                    if (!frm.is_dirty()) await frm.reload_doc();
                    show_result(message);
                }
            } catch (_) {
                // Reconnect automatically after a temporary network failure.
                frm.__report_timer = setTimeout(poll, 10000);
            }
        };
        poll();
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
                for (const category of ["SLD", "Customer Vendor Agreement", "KSEB Agreement"]) {
                    frm.add_custom_button(__(category), async () => {
                        if (frm.__report_starting) return;
                        frm.__report_starting = true;
                        try {
                            if (frm.is_dirty()) await frm.save();
                            const { message } = await frappe.call({
                                method: `${api}.generate_project_document`,
                                args: { project: frm.doc.name, category },
                                freeze: true, freeze_message: __("Generating {0}...", [__(category)]),
                            });
                            if (!message) return;
                            await frm.reload_doc();
                            const warnings = (message.warnings || []).map((value) =>
                                `<li>${escape(value)}</li>`).join("");
                            const blanks = message.missing_fields?.length
                                ? `<p>${__("{0} fields left blank; complete them in {1}.", [message.missing_fields.length, category === "SLD" ? "QElectroTech" : __("a PDF editor")])}</p>` : "";
                            frappe.msgprint({
                                title: __(category),
                                message: `<p><a href="${escape(message.file_url)}" target="_blank" rel="noopener">${__("Download {0}", [__(category)])}</a></p>` +
                                    blanks + (warnings ? `<ul>${warnings}</ul>` : ""),
                            });
                        } finally { frm.__report_starting = false; }
                    }, __("Generate"));
                }
                frm.add_custom_button(__("Generate Project Report"), async () => {
                    if (frm.__report_starting) return;
                    frm.__report_starting = true;
                    try {
                        if (frm.is_dirty()) await frm.save();
                        const { message } = await frappe.call({
                            method: `${api}.generate_project_report`, args: { project: frm.doc.name },
                            freeze: true, freeze_message: __("Collecting report documents..."),
                        });
                        if (message) watch(frm, message.name);
                    } finally { frm.__report_starting = false; }
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
            if (active(frm.doc.custom_project_report_status) && frm.doc.custom_latest_project_report !== frm.__report_completed) {
                watch(frm, frm.doc.custom_latest_project_report);
            }
        },
    });

    frappe.realtime.on("solar_project_report", (report) => {
        const frm = window.cur_frm;
        if (frm?.doctype === "Project" && frm.doc.name === report.project && frm.__report_name === report.name) {
            frm.dashboard.set_headline(escape(`${report.status}: ${report.message || ""}`));
        }
    });
})();
