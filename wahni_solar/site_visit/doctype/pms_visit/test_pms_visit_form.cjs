const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function environment() {
    let handlers;
    const requests = [];
    const context = {frappe: {
        ui: {form: {on(doctype, events) { handlers = events; }}},
        call(args) { return new Promise(resolve => requests.push({args, resolve})); },
    }};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "pms_visit.js"), "utf8"), context);
    const frm = {
        doc: {project: "P1", plant_capacity_kw: 7.25},
        async set_value(values) { Object.assign(this.doc, values); },
    };
    return {handlers, requests, frm};
}

(async () => {
    const {handlers, requests, frm} = environment();
    const queries = {};
    frm.set_query = (field, callback) => { queries[field] = callback; };
    handlers.setup(frm);
    assert.equal(queries.project().filters.status, "Completed");
    assert.equal(queries.project().filters.customer, undefined);
    assert.equal(queries.service_person().query, "wahni_solar.site_visit.api.supervisor_query");
    const pending = handlers.project(frm);
    requests[0].resolve({message: {client_name: "Customer name", customer: "CUSTOMER"}});
    await pending;
    assert.equal(frm.doc.client_name, "Customer name");
    assert.equal(frm.doc.customer, "CUSTOMER");
    assert.equal(frm.doc.plant_capacity_kw, 7.25);
    const stale = handlers.project(frm);
    frm.doc.project = "P2";
    requests[1].resolve({message: {client_name: "Wrong name"}});
    await stale;
    assert.equal(frm.doc.client_name, "Customer name");
    frm.doc.project = "";
    await handlers.project(frm);
    assert.equal(requests.length, 2);
    process.stdout.write("5 PMS form checks passed (project filter, supervisor query, autofill, capacity, stale response).\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
