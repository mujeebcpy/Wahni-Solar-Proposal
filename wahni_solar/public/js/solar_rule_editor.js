/* Shared helpers for editable solar package and material rules. */
frappe.provide("wahni_solar.solar_rule_editor");

(() => {
    const editor = wahni_solar.solar_rule_editor;
    const core_variables = [
        "phase", "cabling_type", "capacity_kw", "panel_capacity_w", "panel_count",
        "inverter_count", "include_battery", "brand", "system_type", "grid_type"
    ];
    const escape = value => frappe.utils.escape_html(String(value ?? ""));

    editor.variables = package_doc => [
        ...core_variables,
        ...(package_doc?.input_definitions || []).map(row => row.variable_key)
    ].filter(Boolean);

    editor.reference = (package_doc, rows = []) => {
        const variables = editor.variables(package_doc).map(escape).join(", ");
        const keys = rows.map(row => row.rule_key || row.template_alias).filter(Boolean).map(escape).join(", ");
        frappe.msgprint({
            title: __("Rule Reference"),
            wide: true,
            message: `<p><strong>${__("Core and package variables")}</strong><br>${variables}</p>
                <p>${__("A template can also use input keys defined by the package that selects it.")}</p>
                <p><strong>${__("Quantity examples")}</strong><br>
                <code>8</code>; <code>db_loop_length</code>; <code>ceil(inverter_count / 7)</code>;<br>
                <code>qty("clamp") * 2</code>; <code>qty("downrun.clamp")</code></p>
                <p>${__("qty() uses a rule key in the same template, or a package alias plus rule key. Excluded rows resolve to zero.")}</p>
                <p><strong>${__("Condition examples")}</strong><br>
                <code>phase == "Three Phase"</code>; <code>include_battery</code>;<br>
                <code>db_meter_distance &gt; 3 and not self_screws</code></p>
                <p>${__("Use arithmetic, comparisons, and / or / not, conditional expressions and approved numeric helpers. Code, imports, attributes and database access are not allowed.")}</p>
                ${keys ? `<p><strong>${__("Keys in this table")}</strong><br>${keys}</p>` : ""}`
        });
    };

    function row_options(rows, key_field) {
        return rows.map((row, index) => `${index + 1}: ${row[key_field] || __("New row")}`);
    }

    editor.condition_builder = (frm, table_field, key_field) => {
        const rows = frm.doc[table_field] || [];
        if (!rows.length) return frappe.msgprint(__("Add a table row first."));
        const dialog = new frappe.ui.Dialog({
            title: __("Build Include Condition"),
            fields: [
                { fieldname: "target", label: __("Row"), fieldtype: "Select", options: row_options(rows, key_field), reqd: 1 },
                { fieldname: "variable", label: __("Variable"), fieldtype: "Autocomplete", options: editor.variables(frm.doc), ignore_validation: true, reqd: 1 },
                { fieldname: "operator", label: __("Comparison"), fieldtype: "Select", options: ["==", "!=", ">", ">=", "<", "<="], reqd: 1 },
                { fieldname: "value_type", label: __("Value Type"), fieldtype: "Select", options: ["Text", "Number", "Check"], default: "Text", reqd: 1 },
                { fieldname: "value", label: __("Compare With"), fieldtype: "Data", description: __("For Check use 0 or 1. Text is quoted automatically.") },
                { fieldname: "combine", label: __("Apply To Existing Condition"), fieldtype: "Select", options: ["Replace", "and", "or"], default: "Replace", reqd: 1 }
            ],
            primary_action_label: __("Apply Condition"),
            primary_action(values) {
                if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(values.variable)) {
                    return frappe.msgprint(__("Use a variable key, such as phase or db_loop_length."));
                }
                let literal;
                if (values.value_type === "Number") {
                    const number = Number(values.value);
                    if (values.value == null || String(values.value).trim() === "" || !Number.isFinite(number)) {
                        return frappe.msgprint(__("Enter a finite numeric comparison value."));
                    }
                    literal = String(number);
                } else if (values.value_type === "Check") {
                    if (!["0", "1"].includes(String(values.value))) {
                        return frappe.msgprint(__("Enter 0 or 1 for a Check value."));
                    }
                    literal = String(values.value) === "1" ? "True" : "False";
                } else {
                    literal = JSON.stringify(values.value || "");
                }
                const row = rows[parseInt(values.target, 10) - 1];
                let expression = `${values.variable} ${values.operator} ${literal}`;
                if (values.combine !== "Replace" && row.include_when) {
                    expression = `(${row.include_when}) ${values.combine} (${expression})`;
                }
                frappe.model.set_value(row.doctype, row.name, "include_when", expression);
                dialog.hide();
            }
        });
        dialog.show();
    };

    editor.quantity_helper = frm => {
        const rows = frm.doc.items || [];
        if (!rows.length) return frappe.msgprint(__("Add a material row first."));
        let dialog;
        dialog = new frappe.ui.Dialog({
            title: __("Enter Quantity Formula"),
            fields: [
                { fieldname: "target", label: __("Material Row"), fieldtype: "Select", options: row_options(rows, "rule_key"), reqd: 1,
                    onchange() {
                        if (!dialog) return;
                        const row = rows[parseInt(dialog.get_value("target"), 10) - 1];
                        if (row) dialog.set_value("formula", row.quantity_formula || "1");
                    } },
                { fieldname: "formula", label: __("Quantity Formula"), fieldtype: "Small Text", reqd: 1 },
                { fieldname: "help", fieldtype: "HTML", options: `<p>${__("Enter a number, a package input key, or an equation. Examples:")}</p>
                    <code>db_loop_length</code><br><code>ceil(inverter_count / 7)</code><br>
                    <code>qty("clamp") * 2</code><br><code>qty("downrun.clamp")</code>
                    <p>${__("Local rule keys:")} ${rows.map(row => escape(row.rule_key)).join(", ")}</p>
                    <p>${__("Save and use Test Rules to validate the formula in a package context.")}</p>` }
            ],
            primary_action_label: __("Apply Formula"),
            primary_action(values) {
                const row = rows[parseInt(values.target, 10) - 1];
                frappe.model.set_value(row.doctype, row.name, "quantity_formula", values.formula);
                dialog.hide();
            }
        });
        dialog.show();
        dialog.set_value("formula", rows[0].quantity_formula || "1");
    };

    function result_html(result) {
        const counts = ["panel_count", "inverter_count"].filter(key => result[key] != null)
            .map(key => `${escape(key)}: ${escape(result[key])}`).join(" · ");
        const warnings = (result.warnings || []).map(value => `<li>${escape(value)}</li>`).join("");
        const rows = result.rows || [];
        let html = counts ? `<p><strong>${counts}</strong></p>` : "";
        if (warnings) html += `<ul>${warnings}</ul>`;
        if (!rows.length) return html + `<p>${__("No material rows were generated. Empty templates are allowed.")}</p>`;
        html += `<div class="table-responsive"><table class="table table-bordered table-condensed">
            <thead><tr>${["Rule", "Component", "Item", "Included", "Quantity", "UOM", "Calculation"].map(value => `<th>${__(value)}</th>`).join("")}</tr></thead><tbody>`;
        html += rows.map(row => `<tr>
            <td>${escape([row.template_alias, row.rule_key].filter(Boolean).join("."))}</td>
            <td>${escape(row.component_label || row.item_name)}</td><td>${escape(row.item_code)}</td>
            <td>${escape(row.included === false || row.included === 0 ? __("No") : __("Yes"))}</td>
            <td>${escape(row.quantity)}</td><td>${escape(row.uom)}</td><td>${escape(row.calculation_note || row.quantity_formula)}</td>
            </tr>`).join("");
        return html + "</tbody></table></div>";
    }

    editor.preview = package_doc => {
        const definitions = package_doc.input_definitions || [];
        const fields = [
            { fieldname: "phase", label: __("Number of Phases"), fieldtype: "Select", options: ["Single Phase", "Three Phase"], default: "Single Phase", reqd: 1 },
            { fieldname: "cabling_type", label: __("Down Run Cabling"), fieldtype: "Select", options: ["Armoured Cabling", "Conduit Cabling"], default: "Armoured Cabling", reqd: 1 },
            { fieldname: "capacity_kw", label: __("System Capacity (kW)"), fieldtype: "Float", default: 3, reqd: 1 },
            { fieldname: "panel_capacity_w", label: __("Panel Capacity (W)"), fieldtype: "Int", default: 660, reqd: 1 },
            { fieldname: "panel_count", label: __("Panel Count Override"), fieldtype: "Int", description: __("Optional. Leave blank to use the calculated count.") },
            { fieldname: "include_battery", label: __("Include Battery"), fieldtype: "Check", hidden: !package_doc.allow_battery, default: 0 },
            { fieldname: "site_inputs", label: __("Package Inputs"), fieldtype: "Section Break" }
        ];
        definitions.forEach((row, index) => {
            fields.push({
                fieldname: `package_input_${index}`,
                label: row.label || row.variable_key,
                fieldtype: row.input_type,
                options: row.input_type === "Select" ? row.select_options : undefined,
                default: row.default_value,
                description: [row.uom, row.show_when ? `${__("Used when")}: ${row.show_when}` : "", row.required ? __("Required when visible") : ""].filter(Boolean).join(" · ")
            });
        });
        fields.push({ fieldname: "result_section", label: __("Test Result"), fieldtype: "Section Break" });
        fields.push({ fieldname: "result", fieldtype: "HTML", options: `<p>${__("Run the test to inspect quantities. This does not create or change a proposal.")}</p>` });
        const dialog = new frappe.ui.Dialog({
            title: `${__("Test Rules")}: ${package_doc.package_title || package_doc.name}`,
            size: "extra-large",
            fields,
            primary_action_label: __("Run Test"),
            async primary_action(values) {
                const inputs = {};
                definitions.forEach((row, index) => {
                    inputs[row.variable_key] = values[`package_input_${index}`];
                    delete values[`package_input_${index}`];
                });
                Object.assign(values, inputs);
                if (!values.panel_count) delete values.panel_count;
                if (!package_doc.allow_battery) values.include_battery = 0;
                try {
                    const { message } = await frappe.call({
                        method: "wahni_solar.wahni_solar_proposal.api.preview_package",
                        args: { package_name: package_doc.name, values: JSON.stringify(values) },
                        freeze: true,
                        freeze_message: __("Testing package rules...")
                    });
                    dialog.get_field("result").$wrapper.html(result_html(message || {}));
                } catch (error) {
                    // frappe.call displays the server's contextual validation error.
                    dialog.get_field("result").$wrapper.html(`<p class="text-danger">${__("The test failed. Correct the reported rule or input and run it again.")}</p>`);
                }
            }
        });
        dialog.show();
    };

    editor.test_template = frm => {
        const dialog = new frappe.ui.Dialog({
            title: __("Choose Package for Test"),
            fields: [{
                fieldname: "package_name", label: __("Solar Package"), fieldtype: "Link", options: "Solar Package", reqd: 1,
                description: __("Select a saved package that links this template. Its input definitions and other templates supply the test context."),
                get_query: () => ({ filters: { disabled: 0 } })
            }],
            primary_action_label: __("Continue"),
            async primary_action(values) {
                const package_doc = await frappe.db.get_doc("Solar Package", values.package_name);
                if (!(package_doc.component_rules || []).some(row => row.component_template === frm.doc.name)) {
                    return frappe.msgprint(__("This package does not link the current template. Select a package that uses it."));
                }
                dialog.hide();
                editor.preview(package_doc);
            }
        });
        dialog.show();
    };
})();
