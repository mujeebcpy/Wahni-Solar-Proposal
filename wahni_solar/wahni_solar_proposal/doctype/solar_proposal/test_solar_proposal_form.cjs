/* Run with node: regression checks for form concurrency and editable counts. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function environment() {
    const handlers = {};
    const requests = [];
    const controls = [];
    const state = {};
    const element = () => ({ empty() {}, text() { return this; }, appendTo() { return this; }, hide() {} });
    const context = {
        __: value => value,
        flt: value => Number(value) || 0,
        cint: value => parseInt(value, 10) || 0,
        $: element,
        locals: {},
        frappe: {
            ui: {form: {
                on(doctype, events) { handlers[doctype] = events; },
                make_control({df}) {
                    // Controls may emit a change while being constructed.
                    df.onchange();
                    const control = {
                        df, value: null,
                        get_value() { return this.value; },
                        set_value(value) { this.value = value; df.onchange(); return Promise.resolve(); }
                    };
                    controls.push(control);
                    return control;
                }
            }},
            call(args) { return new Promise(resolve => requests.push({args, resolve})); },
            prompt(df, callback) { state.prompt_callback = callback; },
            throw(message) { throw new Error(message); },
            utils: {debounce: callback => callback}
        }
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, "solar_proposal.js"), "utf8"), context);
    const frm = {
        doc: {
            package_name: "PACKAGE", calculation_version: "Templates v1",
            capacity_kw: 3, panel_capacity_w: 660, panel_count: 5, suggested_panel_count: 5,
            input_values: [], table_proposal_bom: []
        },
        fields_dict: {input_editor: {$wrapper: element()}},
        dirty_count: 0,
        scheduled_count: 0,
        dirty() { this.dirty_count++; },
        refresh_field() {},
        clear_table(field) { this.doc[field] = []; },
        add_child(field) { const row = {}; this.doc[field].push(row); return row; },
        _preview_debounced() { this.scheduled_count++; }
    };
    return {context, handlers, requests, controls, state, frm};
}

async function test_rapid_capacity_changes_and_manual_panel_count() {
    const {handlers, frm} = environment();
    frm.doc.capacity_kw = 5;
    handlers["Solar Proposal"].capacity_kw(frm);
    assert.equal(frm.doc.panel_count, 8);
    frm.doc.panel_capacity_w = 500;
    handlers["Solar Proposal"].panel_capacity_w(frm);
    assert.equal(frm.doc.panel_count, 10);
    frm.doc.panel_count = 12;
    handlers["Solar Proposal"].panel_count(frm);
    frm.doc.capacity_kw = 6;
    handlers["Solar Proposal"].capacity_kw(frm);
    assert.equal(frm.doc.panel_count, 12);
}

async function test_stale_preview_cannot_replace_a_newer_result() {
    const {context, requests, frm} = environment();
    const older = context.preview(frm);
    const newer = context.preview(frm);
    assert.equal(requests.length, 2);
    requests[1].resolve({message: {project_cost: 222}});
    await newer;
    requests[0].resolve({message: {project_cost: 111}});
    await older;
    assert.equal(frm.doc.project_cost, 222);
    assert.equal(frm.dirty_count, 1);
}

async function test_quantity_edit_invalidates_preview_before_reason_prompt_finishes() {
    const {context, handlers, requests, state, frm} = environment();
    const material = {quantity: 60, override_reason: ""};
    context.locals.BOM = {ROW: material};
    frm.doc.table_proposal_bom = [material];
    const older = context.preview(frm);
    handlers["Solar Proposal BOM Item"].quantity(frm, "BOM", "ROW");
    requests[0].resolve({message: {table_proposal_bom: [{quantity: 50}]}});
    await older;
    assert.equal(frm.doc.table_proposal_bom[0], material);
    assert.equal(material.quantity, 60);
    state.prompt_callback({reason: "Extra supports at the site"});
    assert.equal(material.override_reason, "Extra supports at the site");
    assert.equal(frm.scheduled_count, 1);
}

async function test_input_initialization_does_not_overwrite_values_or_schedule_a_preview() {
    const {context, controls, frm} = environment();
    frm.doc.input_values = [{variable_key: "route_length", label: "Route Length", input_type: "Float", value: "8"}];
    context.render_inputs(frm);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(frm.doc.input_values[0].value, "8");
    assert.equal(frm.dirty_count, 0);
    assert.equal(frm.scheduled_count, 0);
    controls[0].value = 11;
    controls[0].df.onchange();
    assert.equal(frm.doc.input_values[0].value, "11");
    assert.equal(frm.scheduled_count, 1);
}

(async () => {
    for (const test of [
        test_rapid_capacity_changes_and_manual_panel_count,
        test_stale_preview_cannot_replace_a_newer_result,
        test_quantity_edit_invalidates_preview_before_reason_prompt_finishes,
        test_input_initialization_does_not_overwrite_values_or_schedule_a_preview
    ]) await test();
    process.stdout.write("4 proposal form regression checks passed.\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
