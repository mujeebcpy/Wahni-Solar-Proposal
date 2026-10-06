frappe.ui.form.on("Solar Completion Certificate", {
    refresh(frm) {
        if (frm.is_new()) return;
        frappe.call({method: "wahni_solar.solar_project.project_documents.get_document_preview",
            args: {doctype: frm.doctype, name: frm.doc.name},
            callback({message}) {
                if (!message) return;
                const esc = value => frappe.utils.escape_html(String(value ?? ""));
                const rows = Object.entries(message.values)
                    .filter(([key]) => !message.stored_fields.includes(key))
                    .map(([key, value]) => `<tr><th>${esc(key.replaceAll("_", " "))}</th><td>${esc(value)}</td></tr>`).join("");
                const links = message.sources.map(ref => `<a href="/app/${frappe.router.slug(ref.doctype)}/${encodeURIComponent(ref.name)}">${esc(ref.doctype)}: ${esc(ref.name)}</a>`).join(" · ");
                frm.fields_dict.source_preview.$wrapper.html(`<p>${links}</p><p>${__("These values come from the linked records and are refreshed when printing.")}</p><table class="table table-bordered">${rows}</table>`);
            }
        });
    }
});
