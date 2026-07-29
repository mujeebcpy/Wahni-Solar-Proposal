console.log("Solar Proposal JS loaded");

frappe.ui.form.on("Solar Proposal", {
    refresh(frm) {
        calculate_final(frm);
    },

    solar_package(frm) {
        if (!frm.doc.solar_package) {
            return;
        }

        frappe.db.get_value(
            "Solar Package",
            frm.doc.solar_package,
            ["base_price", "capacity_kw"]
        ).then(r => {
            if (r.message) {
                frm.set_value("project_cost", r.message.base_price || 0);

                load_subsidy(frm, r.message.capacity_kw);
            } else {
                frm.set_value("subsidy", 0);
                calculate_final(frm);
            }
        });
    },

    project_cost(frm) {
        calculate_final(frm);
    },

    discount(frm) {
        calculate_final(frm);
    },

    subsidy(frm) {
        calculate_final(frm);
    }
});

function load_subsidy(frm, capacity) {
    frappe.db.get_list("Subsidy Rule", {
        filters: {
            enabled: 1,
            capacity_from: ["<=", capacity],
            capacity_to: [">=", capacity]
        },
        fields: ["subsidy_amount"],
        limit: 1
    }).then(records => {
        if (records.length > 0) {
            frm.set_value("subsidy", records[0].subsidy_amount || 0);
        } else {
            frm.set_value("subsidy", 0);
        }

        calculate_final(frm);
    });
}

function calculate_final(frm) {
    const cost = flt(frm.doc.project_cost);
    const discount = flt(frm.doc.discount);
    const subsidy = flt(frm.doc.subsidy);

    frm.set_value("final_amount", cost - discount - subsidy);
}