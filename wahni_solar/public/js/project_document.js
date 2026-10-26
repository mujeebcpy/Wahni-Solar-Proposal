// Shared form for the four Project documents. Values from linked records are shown
// read-only; only values a user changes are stored, in the hidden `overrides` field.
(() => {
    // Loaded with each of the four DocTypes; register the handlers once.
    if (window.__wahni_project_document_form) return;
    window.__wahni_project_document_form = true;
    const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
    const label = (key) => frappe.utils.to_title_case(key.replaceAll("_", " "));

    function read_overrides(frm) {
        try {
            const value = frm.doc.overrides;
            return (typeof value === "string" ? JSON.parse(value || "{}") : value) || {};
        } catch (_) {
            return {};
        }
    }

    function write_overrides(frm, overrides) {
        const cleaned = Object.fromEntries(Object.entries(overrides).filter(([, value]) => String(value ?? "").trim()));
        frm.set_value("overrides", Object.keys(cleaned).length ? JSON.stringify(cleaned) : null);
        render(frm);
    }

    function render(frm) {
        const preview = frm.__document_preview;
        if (!preview) return;
        const overrides = read_overrides(frm);
        const editable = frm.perm[0]?.write;
        const rows = Object.entries(preview.defaults).map(([key, source]) => {
            const overridden = Object.hasOwn(overrides, key);
            const value = overridden
                ? `${esc(overrides[key])} <span class="indicator-pill orange">${__("Overridden")}</span>
                   <div class="text-muted small">${__("From records")}: ${esc(source) || "—"}</div>`
                : esc(source) || `<span class="text-muted">${__("Not set")}</span>`;
            const actions = !editable ? "" : `
                <button class="btn btn-xs btn-default" data-action="override" data-key="${esc(key)}">${overridden ? __("Edit") : __("Override")}</button>
                ${overridden ? `<button class="btn btn-xs btn-link" data-action="reset" data-key="${esc(key)}">${__("Reset")}</button>` : ""}`;
            return `<tr><th style="width: 30%">${esc(label(key))}</th><td style="white-space: pre-line">${value}</td>
                <td style="width: 1%; white-space: nowrap">${actions}</td></tr>`;
        }).join("");
        const links = preview.sources.map((ref) =>
            `<a href="/app/${frappe.router.slug(ref.doctype)}/${encodeURIComponent(ref.name)}">${esc(ref.doctype)}: ${esc(ref.name)}</a>`
        ).join(" · ");
        const wrapper = frm.fields_dict.source_preview.$wrapper;
        wrapper.html(`<p>${links}</p>
            <p class="text-muted">${__("These values come from the linked records and are refreshed when printing. Override a value only when this document needs something different.")}</p>
            <table class="table table-bordered">${rows}</table>`);
        wrapper.find("button[data-action]").on("click", (event) => {
            const { action, key } = event.currentTarget.dataset;
            const current = read_overrides(frm);
            if (action === "reset") {
                delete current[key];
                write_overrides(frm, current);
                return;
            }
            frappe.prompt(
                [{ fieldname: "value", fieldtype: "Small Text", label: label(key), reqd: 1,
                   default: current[key] ?? preview.defaults[key] ?? "",
                   description: __("From records: {0}", [esc(preview.defaults[key]) || "—"]) }],
                ({ value }) => write_overrides(frm, { ...current, [key]: value }),
                __("Override {0}", [label(key)]), __("Apply"),
            );
        });
    }

    const handlers = {
        refresh(frm) {
            if (frm.is_new()) return;
            frappe.call({
                method: "wahni_solar.solar_project.project_documents.get_document_preview",
                args: { doctype: frm.doctype, name: frm.doc.name },
                callback({ message }) {
                    if (!message) return;
                    frm.__document_preview = message;
                    render(frm);
                },
            });
        },
    };
    for (const doctype of ["Customer Vendor Agreement", "Customer KSEB Agreement", "Solar Installation Checklist", "Solar Completion Certificate"]) {
        frappe.ui.form.on(doctype, handlers);
    }
})();
