# Configurable solar proposal: data-entry tables

Updated on 23 October 2026 from Package.md and the confirmed choices. Each table shows the field name, Frappe type, who fills it, and an example value. The application implements user-maintained systems, templates, Item mappings, conditions and quantity formulas.

- [Read the field-by-field guide](field-guide.md).
- [Setup and staff workflow](implementation.md).
- [Implementation verification](validation.md).
- [Open the editable draw.io tables](wahni-solar-proposal.drawio).
- [View the PDF tables](wahni-solar-proposal.pdf).

| Tab | What it explains |
| --- | --- |
| 1 — Package and template links | System profiles, inverter-count formula, reusable template links and optional Battery / Battery DB |
| 2 — Configurable inputs | Package-defined inputs, typed defaults, saved proposal values and core formula variables |
| 3 — Component Template | Generic component labels, actual Item links, inclusion conditions and quantity formulas on the same row |
| 4 — Rule entry examples | Phase-specific cables, quantity dependencies, test previews and validation behavior |
| 5 — Solar Proposal | Main inputs, optional battery, extra site inputs and saved material / valuation results |
| 6 — Existing charges and PDF | Current cost child fields and formulas, valuation context and final PDF steps |

Confirmed decisions:

- Staff choose the actual ERPNext Item once in each template material row; proposals use it automatically. A separate generic Component master is unnecessary for this stage.
- Staff can define extra proposal inputs with typed defaults on a package. No new application field is required for each additional distance or installation choice.
- Battery and Battery DB are optional additions to compatible hybrid systems. Battery is not a standalone system profile in this design.
- Material selection and quantities come from editable conditions and expressions, including dependencies on other material quantities. There is no fixed item catalogue or fixed set of component groups in program code.
- Material pricing uses company/warehouse valuation estimates for now. New pricing and margin rules are deferred. Existing panel/labour/other defaults remain in Wahni Default Settings → Cost Calculation.
- Saved proposals retain their input values, Item mappings, quantities, rates and explanations until explicitly regenerated or repriced. Template edits and default changes do not rewrite history.

Panel Count is editable in the proposal. The server suggests a count from capacity and panel wattage; inverter counts, materials, installed capacity and automatic charge quantities use the selected count.

See [setup and verification](implementation.md) for installation, demo cleanup, migration behavior and the working proposal flow. The field guide is updated for editable panel counts; the diagram/PDF show the original design and should be read with that change in mind. The existing panel-cost basis and Include Structure behavior remain recorded as costing follow-ups. Demo materials illustrate data entry and must be reviewed by staff.
