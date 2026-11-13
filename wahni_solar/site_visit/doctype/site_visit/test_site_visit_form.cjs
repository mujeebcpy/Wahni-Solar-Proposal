const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function environment() {
    const requests = [];
    const routes = [];
    let handlers;
    const context = {
        __: value => value,
        frappe: {
            ui: {form: {on(doctype, events) { handlers = events; }}},
            call(args) { return new Promise(resolve => requests.push({args, resolve})); },
            set_route(...args) { routes.push(args); },
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "site_visit.js"), "utf8"), context);
    const frm = {
        doc: {solar_proposal: "P1"},
        is_new: () => true,
        async set_value(values) { Object.assign(this.doc, values); },
    };
    return {handlers, requests, routes, frm};
}

async function test_list_created_report_fetches_defaults_from_selected_proposal() {
    const {handlers, requests, frm} = environment();
    const pending = handlers.solar_proposal(frm);
    assert.equal(requests[0].args.args.source_name, "P1");
    requests[0].resolve({message: {__islocal: 1, customer_name: "Customer", requested_capacity_kw: 5, lead: "L"}});
    await pending;
    assert.equal(frm.doc.customer_name, "Customer");
    assert.equal(frm.doc.lead, "L");
    assert.equal(frm.doc.requested_capacity_kw, 5);
}

async function test_manual_values_survive_but_untouched_defaults_follow_proposal() {
    const {handlers, requests, frm} = environment();
    frm.doc.customer_name = "Manual name";
    frm.doc.requested_capacity_kw = 5;
    frm._proposal_defaults = {customer_name: "Previous name", requested_capacity_kw: 5};
    const pending = handlers.solar_proposal(frm);
    requests[0].resolve({message: {__islocal: 1, customer_name: "New name", requested_capacity_kw: 8, lead: "NEW-LEAD"}});
    await pending;
    assert.equal(frm.doc.customer_name, "Manual name");
    assert.equal(frm.doc.requested_capacity_kw, 8);
    assert.equal(frm.doc.lead, "NEW-LEAD");
}

async function test_stale_response_is_ignored() {
    const {handlers, requests, frm} = environment();
    const pending = handlers.solar_proposal(frm);
    frm.doc.solar_proposal = "P2";
    requests[0].resolve({message: {__islocal: 1, customer_name: "Stale"}});
    await pending;
    assert.equal(frm.doc.customer_name, undefined);
}

async function test_existing_report_is_opened_and_saved_reports_do_not_refetch() {
    const {handlers, requests, routes, frm} = environment();
    const pending = handlers.solar_proposal(frm);
    requests[0].resolve({message: {name: "SV-EXISTING"}});
    await pending;
    assert.deepEqual(routes[0], ["Form", "Site Visit", "SV-EXISTING"]);
    frm.is_new = () => false;
    await handlers.solar_proposal(frm);
    assert.equal(requests.length, 1);
}

(async () => {
    for (const test of [
        test_list_created_report_fetches_defaults_from_selected_proposal,
        test_manual_values_survive_but_untouched_defaults_follow_proposal,
        test_stale_response_is_ignored,
        test_existing_report_is_opened_and_saved_reports_do_not_refetch,
    ]) await test();
    process.stdout.write("4 Site Visit form regression checks passed.\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
