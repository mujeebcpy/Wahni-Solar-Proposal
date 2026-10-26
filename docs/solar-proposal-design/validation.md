# Implementation verification — 23 October 2026

Verified against the **local development database** `erpbeta.wahni.in`. A normal full site backup completed before migration. Both migration patches completed, and a second migration completed successfully without recreating or changing staff data.

- 120 focused Python tests passed, covering configuration, rule safety, input types, costing, saved snapshots, demo cleanup, migration, proposal validation, print rendering and downstream Project/Sales Order compatibility.
- Four JavaScript form regression checks passed, covering panel count edits, rapid input changes, stale responses, override prompts and input initialization. Changed JavaScript files also passed syntax checks.
- Created and saved a separate test template/package with actual site Items and required site measurements. Verified phase conditions, hidden inputs, count calculations, material overrides and explicit regeneration. Temporary test records were rolled back.
- Cleared all eight demo configuration records, verified the opt-out prevented reseeding, and explicitly reinstalled two packages and six templates. Actual Item count remained 369. The demo discovery selects actual AC cables, microinverter, supports, screws, plugs and an earthing rod already on the site.
- Verified a draft with a missing material UOM conversion can save but cannot print a final customer PDF. Verified battery inclusion is optional on the hybrid example.
- Compared all four original proposals against the private migration archive: panel counts, material costs, other charges, project totals, discounts, subsidies and final totals were preserved. All six retired package columns are absent. Referenced old packages remain disabled.

The saved demo proposal is **WGT-SQ-26-27-012**, using **DEMO — Micro Inverter System**:

| Result | Value |
| --- | --- |
| Requested system / panel wattage | 3 kW / 660 W |
| Server suggestion / selected panels | 5 / 7 |
| Inverters / installed panel capacity | 7 / 4.62 kWp |
| Material rows | 8 |
| Material valuation / existing other charges | ₹60,718 / ₹213,180 |
| Project total / configured subsidy | ₹273,898 / ₹78,000 |
| Customer effective cost | ₹195,898 |
| PDF | Four pages, with existing artwork and grouped bill of materials |

Generated PDF text was checked for counts and actual Item names; all four pages were visually inspected for layout. The review copy is `/tmp/wahni-solar-demo-proposal.pdf`. A temporary local web server supplied PDF assets during the CLI check; no site hostname configuration was changed.

Existing **Solar Proposal Content** text is retained. Its current Note and Customer Scope still contain statements excluding structure/subsidy that can conflict with configured charges and deductions. Review those business terms before using the new format for customer delivery. The existing Panel Cost wattage basis and Include Structure pricing behavior remain recorded for the next pricing stage.
