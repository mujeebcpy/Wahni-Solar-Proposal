# Working package and proposal configuration

Run `bench --site <site> migrate` after updating the app. The migration installs the new DocTypes, updates the standard Solar Proposal print format, and configures editable demo records using suitable stock Items already present on that site. It never creates inventory Items or valuation rates.

All proposal records are grouped under the **Wahni Solar Proposal** workspace (`/desk/wahni-solar-proposal`), shown as **Solar Proposal** on the Wahni Solar dock beside Solar Project and Solar Monitor. Its sidebar lists Solar Proposal, Solar Package, Component Template, Proposal Content (under Setup) and Settings.

## Staff workflow

1. Open **Solar Component Template**. Choose a group name such as Downrun. Add a stable rule key, generic component label, actual ERPNext Item, UOM, quantity formula and optional inclusion condition on each row. Empty templates are allowed.
2. Open **Solar Package**. Choose system metadata and an inverter count formula. Add additional typed site inputs with literal defaults, then attach templates using unique aliases. For example, attach Downrun as `downrun`; other templates can refer to `qty("downrun.clamp")`.
3. Use **Test Rules** on the saved package. Enter phases, cabling, capacity, panel wattage and site measurements. The preview explains included and excluded rows and reports invalid references or cycles.
4. Create a **Solar Proposal**. Select a party and package, phases, cabling, capacity and panel wattage. Review Additional Site Inputs. The suggested panel count comes from the server; **Panel Count is editable**. For a 3 kW system with 660 W panels the suggestion is 5, but staff may select 7. All inverter/material formulas and automatic charge quantities then use 7.
5. Review generated materials and existing **Other Charges**. Direct material quantity changes require an override reason; dependent formulas use the overridden quantity. Add/remove material definitions in the templates. Update a saved proposal from current templates using **Configuration → Regenerate Materials**, which resets direct material overrides. **Refresh Valuation** updates cost rates without loading current template definitions.
6. Save, then **Print → Solar Proposal → PDF**. The customer format includes saved system details, grouped materials, pricing deductions and existing proposal content. Missing valuation or UOM conversion is permitted in a draft and blocks the final PDF until resolved.

Company and Valuation Warehouse default from **Wahni Default Settings**. Rates use the chosen warehouse's positive Bin valuation rate, otherwise the Item's positive valuation rate. A selected material UOM uses its defined conversion factor. No buying/selling price-list fallback is used. Saved proposals retain rule definitions, input metadata, Item descriptions, rates and amounts until edited or explicitly refreshed.

The existing Project Cost Breakdown child table is retained. Its automatic quantities track staff-selected panel count, while manual quantity edits persist. The hidden `calculated_quantity` field identifies an automatic quantity across draft previews. Existing Panel Cost still uses `panel_max_cacpacity` from Settings as its per-panel wattage basis; changing pricing/margin rules is a separate stage. Structure inclusion behavior is preserved.

## Demo defaults

As System Manager, open **Wahni Default Settings → Demo**:

- **Install Demo Defaults** creates missing tagged demo packages/templates without replacing staff edits.
- **Clear Demo Defaults** removes demo proposals, packages and templates where normal link checks permit deletion. Records used by real proposals/projects or containing staff uploads are retained and reported. Actual Items, transactions and stock values are preserved.

Clearing defaults sets an opt-out flag, so later migrations do not recreate them. Install Demo Defaults explicitly resets that flag. The sample catalogue is illustrative: staff must review Item specifications and fill in any missing component definitions.

## Legacy cleanup

The pre-sync patch archives old package settings, proposal/material rows and Item descriptions in the site's private `backups/wahni-solar-legacy-configuration-v1.json`, with owner-only file permissions. The post-sync patch removes six retired Solar Package columns: `inverter_bom_item`, `basic_bom_item`, `connection_type`, `panel_capacity_min`, `panel_capacity_max`, and `description`. It removes unreferenced old packages and disables referenced ones.

Existing proposals remain marked **Legacy**, with their saved material quantities, rates and totals. They can still print. Their phase and system metadata are preserved before old package columns are removed. Select a new enabled package, enter the panel wattage and use Regenerate Materials to convert one deliberately. Shared material/charge child tables remain because proposals and Projects use them. Core ERPNext Item and manufacturing BOM records are retained.

Both migration patches are marked `never_skip_patches`; failed archival must stop the migration. The private archive supplements the regular full site backup and is not a substitute for it.

## Validation

The application tests cover bounded rule evaluation, phase conditions, dependencies and cycles, direct overrides, editable panel counts, typed inputs, draft charge recalculation, UOM conversion, saved snapshots, demo cleanup, migration archival and Project/Sales Order compatibility. New proposal valuation costs are not copied as Sales Order selling prices; ERPNext supplies selling prices through its normal pricing flow.
