# Configurable Solar Package and Proposal — field tables

Design updated on 23 October 2026 from Package.md and the confirmed decisions below. These are proposed DocTypes/fields; application code has not been changed.

- Staff select the actual ERPNext Item once on a template material row; proposals copy that choice.
- Packages define additional proposal inputs with typed defaults, without new application fields or code.
- Battery and Battery DB are optional additions to compatible hybrid packages, not a separate system.
- Material rows use valuation estimates for this stage. Keep the current other-charge child table; pricing and margin redesign are deferred.
- Systems, template groups, actual Items, inclusion conditions and quantity equations are editable records, not a predefined catalogue in program code.

**Entry order:** define package inputs → configure reusable templates and their Item mappings/rules → link templates to the package → test the package → generate a proposal → review existing charges → print PDF.

The examples illustrate how to enter rules. They are not a prescribed electrical design or an inventory import. Formula syntax shown is the proposed expression language.

## 1 - Package and template links

A system is a Package record. Staff can add future systems and component groups without changing the calculation program.

### Solar Package — parent fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Package Name<br>package_title | Data | Staff enters | A named system profile, including any compatible hybrid combination. |
| Brand<br>brand | Link → Brand | Staff selects existing metadata | Brand used for display / existing print content. |
| System Type<br>system_type | Select | Staff selects existing metadata | Micro / String / Hybrid. |
| Grid Type<br>grid_type | Select | Staff selects existing metadata | On-Grid / Off-Grid / Hybrid. |
| Inverter Count Formula<br>inverter_count_formula | Small Text — expression | Staff enters per package | panel_count; ceil(panel_count / 2); or a count rule appropriate to this system. |
| Allow Battery<br>allow_battery | Check | Staff enables only for compatible hybrid packages | When false, the proposal has include_battery = false. |
| Component Templates<br>component_rules | Table → Solar Package Component Rule | Staff selects templates and optional conditions | Downrun, inverter links, looping, common protection, DB templates and optional battery templates. |
| Additional Input Definitions<br>input_definitions | Table → Solar Package Input | Staff adds inputs and defaults | Lengths, installation choices and any other variables used by the rules. |
| Disabled<br>disabled | Check | Optional staff choice | Stops selection for new proposals; does not change saved proposals. |

### Solar Package Component Rule — child table of Package

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Template Alias<br>template_alias | Data | Staff enters a stable unique key within the package | downrun / inverter_links / common / battery_db. |
| Component Template<br>component_template | Link → Solar Component Template | Staff selects a reusable saved template | A Downrun or Common Protection template. |
| Include When<br>include_when | Small Text — boolean expression | Blank = always; staff may enter a condition | include_battery enables the whole battery template. |
| Enabled<br>enabled | Check | Defaults Yes; staff can turn off a mapping | Disabled mappings contribute zero quantities. |

Phase and cabling conditions can be entered here for an entire template, or on individual material rows. Multiple templates can contribute to the same display group. Do not require a fixed number of groups.

### Example: package template mappings — names are illustrative

| Alias | Template selected | Include When | Meaning |
| --- | --- | --- | --- |
| downrun | A suitable Downrun template | Always | Uses the phase/cabling inputs where its rows need them. |
| inverter_links | Micro Inverter to Downrun | Always | Inverter cables / accessories for this package. |
| db_loop | Downrun to DB Looping | Always | Phase-specific looping cables. |
| common | Common Protection | Always | Reusable common materials. |
| battery | Battery Materials | include_battery | Only selected when this compatible hybrid includes a battery. |
| battery_db | Battery DB | include_battery | Uses the same optional battery choice. |

Battery is an add-on: staff enable Allow Battery on the applicable hybrid packages, then add conditional Battery / Battery DB template links. Changing to an incompatible package clears the battery choice before generation.

Aliases are stable reference names. For example, qty("downrun.clamp") means the clamp row in the template attached with alias downrun. Reusing a template in another package does not depend on its display name or visual row order.

No template header or package requires a manufactured Item or manufacturing BOM. Existing legacy proposals retain their saved quantities, rates and totals. Regenerate Materials explicitly converts a proposal using an enabled template package.

## 2 - Configurable inputs

The five main selections remain. Each package can define extra lengths and installation choices; their values are saved on the proposal.

### Solar Package Input — child table of Package

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Variable Key<br>variable_key | Data | Staff enters once | db_loop_length; unique and different from core variable / helper names. |
| Label<br>label | Data | Staff enters | DB Looping Length. |
| Input Type<br>input_type | Select | Staff selects | Int / Float / Check / Select / Data. |
| Unit<br>uom | Link → UOM | Optional staff selection | Meter for a route length. |
| Default Value<br>default_value | Data | Staff enters a literal of the chosen type | 8 for Float, or 0 / 1 for Check. A default is not a formula. |
| Choices<br>select_options | Small Text | For Select inputs only | One permitted choice per line. |
| Show When<br>show_when | Small Text — boolean expression | Blank = always; optional condition | include_battery for a battery quantity input. |
| Required<br>required | Check | Staff chooses | A visible required input must have a valid value before its rule is evaluated. |

### Example definitions entered by staff

| Variable key | Type / unit | Default | Use / visibility |
| --- | --- | --- | --- |
| downrun_length | Float / Meter | A default appropriate to the package | The route length used by that package; staff may change it for a site. |
| db_loop_length | Float / Meter | 8 in this example | Quantity of each selected DB looping conductor. |
| db_meter_distance | Float / Meter | Blank; required when the selected rules need it | The above-3-metre condition in Package.md. |
| self_screws | Check | Staff-defined 0 or 1 | Whether wall plugs are needed. |
| battery_count | Int | 1 in this example | Shown only when include_battery is true. |

### Solar Proposal Input Value — child table of Proposal

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Variable Key<br>variable_key | Data — saved copy | Auto from package definition | db_loop_length. |
| Label / Type / Unit<br>label / input_type / uom | Data / Select / Link → UOM | Auto; saved with the proposal | DB Looping Length / Float / Meter. |
| Choices / Show When / Required<br>select_options / show_when / required | Small Text / Small Text / Check | Saved copies of the input definition | Existing proposals keep their original choices, visibility and validation when a package definition changes. |
| Value<br>value | Data | Defaults once; staff edits per proposal | 8. Server converts and validates it as Float from the saved input_type. |

The stored value field has one Frappe fieldtype. The form can display a number, checkbox or choices, while the server parses the value according to its input definition. Template/default edits do not rewrite saved proposal inputs.

### Core variables available to conditions and formulas

| Expression variable | Comes from | Example | Staff can redefine it? |
| --- | --- | --- | --- |
| phase | Proposal.connection_type | Three Phase | No; select it on the proposal. |
| cabling_type | Proposal.down_run_cabling | Armoured Cabling / Conduit Cabling | No; select it on the proposal. |
| capacity_kw / panel_capacity_w | The two capacity inputs | 3 kW / 660 W | No; enter values on the proposal. |
| suggested_panel_count | ceil(capacity_kw × 1000 / panel_capacity_w) | 5 | Server suggestion. |
| panel_count | Actual staff-selected panel count; initially the suggestion | 7 | Yes; all downstream quantities use this count. |
| inverter_count | The selected package inverter-count formula | 5 or 3, depending on package | Edit the package formula, not this saved result. |
| include_battery | Proposal battery choice and package compatibility | True / False | No; choose it on a compatible proposal. |

Inverter-count formulas may reference core inputs, panel_count and package-defined inputs. They may not reference component quantities, which are calculated after inverter_count. Missing required values are errors, not assumed zeroes. Regeneration preserves existing site-entered values, refreshes their definition metadata and applies defaults only to newly introduced keys; incompatible values are reported for staff to correct.

## 3 - Component Template

Generic names describe a component. Staff choose its actual ERPNext Item once here, and proposals use that Item automatically.

### Solar Component Template — parent fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Template Name<br>template_name | Data | Staff enters | A reusable name such as Common Protection or a particular Downrun variant. |
| Display Group<br>group_name | Data | Staff enters an editable group name | Downrun / Micro Inverter to Downrun / Downrun to DB Looping / Common for all / another group. |
| Material Rules<br>items | Table → Solar Component Template Item | Staff adds / removes / edits rows anytime | Each row selects one actual Item and contains its inclusion and quantity rules. |
| Validation Condition<br>validation_condition | Small Text — optional boolean expression | Optional staff-defined supported-input check | Validate a configured range instead of extrapolating beyond the defined rules. |
| Validation Message<br>validation_message | Small Text | Staff explains a failed validation condition | A clear instruction when this template does not support the selected inputs. |
| Notes / Disabled<br>notes / disabled | Small Text / Check | Optional staff entries | Notes and optional retirement; no approval workflow. Empty templates are allowed. |

### Solar Component Template Item — material-rule child fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Rule Key<br>rule_key | Data | Staff enters a stable unique key | yellow_ac_cable; used by references, not the editable label or row index. |
| Generic Component Label<br>component_label | Data | Staff enters | Yellow AC cable, 6 sq.mm. |
| Actual ERPNext Item<br>item_code | Link → Item | Staff selects once in the template | The exact Item to supply and value. Do not guess from the generic name. |
| UOM<br>uom | Link → UOM | Defaults from Item; staff confirms | The quantity formula returns this unit, for example Meter. |
| Include When<br>include_when | Small Text — boolean expression | Blank = always; staff may edit | phase == "Three Phase". |
| Quantity Formula<br>quantity_formula | Small Text — numeric expression | Staff enters a number or equation | 8; db_loop_length; ceil(inverter_count / 7); qty("clamp") * 2. |
| Specification<br>description | Small Text | Defaults from Item; optional template-specific text | Saved in the generated material row for printing. |
| Enabled<br>enabled | Check | Defaults Yes; staff may disable | A disabled row generates zero quantity. |
| Notes<br>notes | Small Text | Optional staff explanation | Why the item is included and what its formula means. |

Example: replace the selected Item with another suitable actual Item while keeping component_label, include_when and quantity_formula. The rule stays attached to the material role; UOM and conversion must still be valid.

### Staff actions provided by the template editor

| Action | Staff does | System shows | Stored result |
| --- | --- | --- | --- |
| Choose Item | Select an actual Item from ERPNext | Item name, stock UOM and description | A direct Item link, not a name-matching search rule. |
| Build a condition | Pick a variable, comparison and value; combine conditions if needed | The equivalent readable boolean expression | include_when on the material row or package-template link. |
| Enter a quantity | Enter a constant, arithmetic or approved helper | Available variables and existing quantity keys | quantity_formula on the material row. |
| Test Rules | Supply sample inputs | Included / excluded rows, substitutions, calculated quantity and errors | No proposal changes until successful generation is applied. |

No separate generic Component master is required for this stage. Reusable templates share their Item choices across packages. Each enabled material rule must select an actual Item before it can generate a priced proposal; staff may keep an empty template and add its rules later.

## 4 - Rule entry examples

Examples show the structure of editable data. Actual Items and electrical specifications are chosen by staff, not seeded by the program.

### Example: Downrun to DB Looping template

| Rule key / generic label | Actual Item / UOM | Include When | Quantity Formula |
| --- | --- | --- | --- |
| red_ac_cable / Red AC cable, 6 sq.mm | Staff-selected red Item / Meter | Always | db_loop_length |
| black_ac_cable / Black AC cable, 6 sq.mm | Staff-selected black Item / Meter | Always | db_loop_length |
| yellow_ac_cable / Yellow AC cable, 6 sq.mm | Staff-selected yellow Item / Meter | phase == "Three Phase" | db_loop_length |
| blue_ac_cable / Blue AC cable, 6 sq.mm | Staff-selected blue Item / Meter | phase == "Three Phase" | db_loop_length |

With db_loop_length = 8, Single Phase generates red and black at 8 metres each. Three Phase generates all four at 8 metres each. The form supplies phase; the additional-input table supplies db_loop_length.

### Example: dependent quantities within a Downrun template

| Rule key | Quantity Formula | Required information | Result for the example |
| --- | --- | --- | --- |
| ug_cable | downrun_length | downrun_length = 25 metres | 25 metres |
| clamp | qty("ug_cable") * 2 | Calculated cable quantity | 50 clamps |
| screw | qty("clamp") * 2 | Calculated clamp quantity | 100 screws |
| wall_plug | 0 if self_screws else qty("screw") | Screw quantity and self_screws input | 0 for self screws, otherwise 100 |
| q_terminal (in an inverter template) | ceil(inverter_count / 7) | Calculated inverter count | 7 inverters → 1; 8 inverters → 2 |

qty("clamp") refers to a rule key within the same template instance. qty("downrun.clamp") uses the package mapping alias to refer to a row in another template. Conditions and formulas both participate in dependency checking.

### Supported expressions and required validation

| Feature | Example / behavior | What staff can change | What the program checks |
| --- | --- | --- | --- |
| Arithmetic and rounding | ceil(downrun_length / 3), min(...), max(...) | Numeric constants, variables and approved arithmetic | Numeric, finite, non-negative quantities and whole-number UOM rules. |
| Conditions | phase == "Three Phase" and db_meter_distance > 3 | Comparisons, and / or / not, and conditional quantities | Boolean result, known variables and valid required inputs. |
| Supported ranges | Template validation plus non-overlapping range conditions | The input ranges and formulas staff have defined | Report an unsupported range; do not silently invent an equation outside it. |
| Dependencies | Cable → clamp → screw → wall plug | References using stable aliases / rule keys | Unknown references and cycles are errors. Excluded known rows/templates resolve to zero. |
| Expression limits | Only approved variables and helpers | Formula data; no server scripting | No imports, attributes, database access or unrestricted Python evaluation. |

Route length is separate from total conductor quantity. Red 35 m plus black 35 m does not automatically make a 70 m conduit route. Staff should reference the intended route input explicitly.

### Acceptance examples for the first implementation

| Scenario | Expected result |
| --- | --- |
| Staff changes Item selection or a template equation | The next generation uses it; saved proposals remain unchanged. |
| Staff adds a package input with a default | It appears on new proposals without a new DocType field or code change. |
| Conditional panel-count bands / distance thresholds | Use only the configured matching branch, including exact boundary values. |
| Compatible hybrid: battery on / off | Battery and Battery DB templates are included / excluded together. |
| Package does not allow battery | include_battery is false; no battery templates are generated. |
| Missing input, misspelled key, cycle or invalid quantity | Show the affected template and row; do not partially replace a saved proposal. |
| No valuation or missing UOM conversion | Material calculation remains inspectable; cost status is unresolved rather than silently priced at zero. |

## 5 - Solar Proposal

Choose the five main inputs, complete package-defined site values, then generate and review the proposal. Battery is optional on compatible hybrids.

### Solar Proposal — staff-entered and defaulted fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Party Type / Party<br>proposal_to / party | Link → DocType / Dynamic Link | Staff selects the existing Customer, Lead or Prospect | Existing party flow is retained. |
| Proposal Date<br>proposal_date | Date | Defaults today; staff may change | The proposal document date. |
| System / Package<br>package_name | Link → Solar Package | Main input 1 | A configured system profile. |
| Number of Phases<br>connection_type | Select | Main input 2 | Single Phase / Three Phase; available as phase in expressions. |
| Down Run Cabling<br>down_run_cabling | Select | Main input 3 | Armoured Cabling / Conduit Cabling; available as cabling_type. |
| System Capacity<br>capacity_kw | Float | Main input 4 | Requested system capacity in kW. |
| Panel Capacity<br>panel_capacity_w | Int | Main input 5 | Selected panel wattage. |
| Include Battery<br>include_battery | Check | Only shown / selectable when the package allows it | Enables the battery-related template mappings. |
| Additional Inputs<br>input_values | Table → Solar Proposal Input Value | Defaults from package definitions; staff edits site values | Lengths, screw choice, battery count and other configured variables. |
| Panel Brand / Include Structure<br>panel_brand / include_structure | Select / Check | Existing staff choices | Retain current fields; see the costing notes on tab 6. |
| Company<br>company | Link → Company | Defaulted from settings / ERPNext | Company context and base currency for valuation. |
| Valuation Warehouse<br>valuation_warehouse | Link → Warehouse | Defaulted from settings; staff confirms | A non-group warehouse belonging to the selected company. |
| Discount / Subsidy<br>discount / subsidy | Currency / Currency | Existing inputs / subsidy default behavior | No new discount, subsidy or margin model in this stage. |
| Remarks<br>remarks_field | Small Text | Optional staff entry | Site-specific information. |

### Solar Proposal — generated / saved result fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Customer Name<br>customer_name | Data | Auto from party | Existing behavior. |
| Suggested Panel Count<br>suggested_panel_count | Int, read-only | Server: ceil(capacity_kw × 1000 / panel_capacity_w) | 3 kW / 660 W → 5 panels. |
| Panel Count<br>panel_count | Int, editable | Staff keeps or changes the suggestion | Selecting 7 panels recalculates inverters, materials, installed capacity and automatic charge quantities. |
| Inverter Count<br>inverter_count | Int | Auto from the package count formula | The count variable used by this package’s material rules. |
| Installed Panel Capacity<br>actual_capacity_kw | Float | Auto: panel_count × panel_capacity_w / 1000 | 5 × 660 W → 3.3 kWp. |
| Material List<br>table_proposal_bom | Table → Solar Proposal BOM Item | Auto after conditions, dependencies and quantities succeed | Actual Items from all applicable package templates. |
| Existing Other Charges<br>cost_breakdown | Table → Project Cost Breakdown | Copy existing defaults and calculate current charges | Staff can review and edit current charge rows. |
| Material / Other Cost<br>material_cost / other_cost | Currency / Currency | Auto | Valued material amounts / included existing charges. |
| Project / Final Amount<br>project_cost / final_amount | Currency / Currency | Auto | Materials + other charges; then existing discount / subsidy deductions. |
| Currency / Cost Status<br>currency / costing_status | Link → Currency / Select | Auto | Company currency; Complete or Missing Valuation / Conversion. |
| Calculation Definition Snapshot<br>configuration_snapshot | JSON — system-managed | Auto when generated; retained on ordinary save / reopen | Saved package formula, input definitions, template mapping conditions and material rules used to generate this proposal. |

Save the input values, chosen Item mappings, quantities, rule explanations and rates with the proposal. Editing a template, an Item or a package default does not silently rewrite those saved results.

### Solar Proposal BOM Item — existing material child, extended for traceability

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Group / Generic Label<br>component_group / component_label | Data / Data | Copied from the template and rule | The role/group used to explain and print the material. |
| Source Template / Alias / Rule<br>source_template / template_alias / rule_key | Link → Solar Component Template / Data / Data | Auto | A stable trace back to the definition that generated the row. |
| Item<br>item_code | Link → Item | Copied automatically from the template | The actual Item staff selected once during template setup. |
| Item Name / Specification<br>item_name / description | Data / Small Text | Saved copies | The material text used by the proposal PDF. |
| Quantity / UOM<br>quantity / uom | Float / Link → UOM | Calculated from the rule; staff may make a recorded site override | Quantity expressed in the template row UOM. |
| Generated Quantity / Override Flag<br>generated_quantity / has_quantity_override | Float / Check | Auto; preserve the calculated basis and record an override | If a clamp quantity is overridden, dependent screw / plug formulas use the effective overridden quantity. |
| Valuation Rate<br>rate | Currency | Auto; per row UOM | Stock-unit valuation converted to the material UOM. |
| Amount<br>amount | Currency | Auto | quantity × rate. |
| Calculation Note<br>calculation_note | Small Text | Auto snapshot | Formula and substituted values explaining the result. |
| Rate Status / Override Reason<br>valuation_status / override_reason | Select / Small Text | Auto status; staff explains any site override | Missing valuation is visibly different from a confirmed zero-rate row. |

Site quantity overrides apply to included rows, are recorded with a reason, and feed dependent calculations. For example, overriding clamps from 50 to 60 makes a two-screws-per-clamp formula produce 120 screws. Excluded rows stay at zero. Ordinary recalculation uses saved definitions and rates; it does not reload edited master records.

Regenerate deliberately reloads current definitions and replaces the generated snapshot only after the complete calculation succeeds. It preserves site-entered input values, adds defaults for new inputs, and explicitly resets direct material-quantity overrides. Reprice refreshes valuation estimates without changing material quantities. Ordinary save / reopen preserves the existing snapshots and overrides.

All evaluations and final totals use one server calculation service. The form previews the same service; API-created proposals and browser edits must pass the same validation.

## 6 - Existing charges and PDF

This stage builds the configurable material engine. Price lists, new markup methods and margin redesign are outside this stage.

### Wahni Default Settings — existing charge defaults and valuation context

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Cost Calculation<br>table_cost_calculation | Table → Project Cost Breakdown | Staff maintains existing default rates | The same ten cost-component options remain. |
| Subsidy Rules<br>table_subsidy_rule | Table → Subsidy Rule | Staff maintains existing ranges / amounts | Keep the current subsidy behavior. |
| Existing Panel Settings<br>panel_min_capacity / panel_max_cacpacity | Int / Int | Existing values retained | The current Panel Cost calculation uses panel_max_cacpacity. |
| Default Costing Company<br>costing_company | Link → Company | Staff sets a default | One company/base-currency context for material valuation. |
| Default Valuation Warehouse<br>valuation_warehouse | Link → Warehouse | Staff sets a non-group warehouse in that company | No arbitrary warehouse selection or hidden buying-price fallback. |

### Project Cost Breakdown — retain the current six fields

| Field / internal field name | Frappe type / linked DocType | Who fills it? | Example / purpose |
| --- | --- | --- | --- |
| Cost Component<br>cost_component | Select | Defaults from settings; staff may change | One of the existing ten components below. |
| Rate<br>rate | Currency | Staff maintains defaults / proposal adjustments | Rate basis depends on the existing component. |
| Quantity<br>quantity | Float | Current automatic default; staff may edit | Panel count, ceil(panel count / 2), requested kW or 1. |
| Included<br>included | Check | Existing default; staff may toggle | Unchecked → zero amount. |
| Amount<br>amount | Float — existing field type | Auto | Current formula for the chosen cost component. |
| Calculation Note<br>calculation_note | Data | Auto explanation | Show the units / basis used by the charge. |

### Current charge formulas — no margin redesign

| Cost Component | Default quantity | Rate basis | Current included amount |
| --- | --- | --- | --- |
| Panel Cost | panel_count | Per watt | rate × settings.panel_max_cacpacity × panel_count |
| Structure Material | ceil(panel_count / 2) | Per two-panel set | rate × quantity |
| Labour Structural | ceil(panel_count / 2) | Per two-panel set | rate × quantity |
| Labour Electrical | ceil(panel_count / 2) | Per two-panel set | rate × quantity |
| Supervisor Documentation and Visits | 1 | Per project | rate |
| Sales Commission | capacity_kw | Per requested kW | rate × capacity_kw |
| Shipping | 1 | Per project | rate |
| Margin | 1 | Fixed amount per proposal | rate; no percentage / markup model added |
| Walk Way | 0; optional staff entry | Staff’s chosen quote basis | rate × quantity when included |
| Ladder | 0; optional staff entry | Staff’s chosen quote basis | rate × quantity when included |

Current-code notes: Panel Cost uses the global maximum panel wattage, and Include Structure does not currently switch off structure charge rows. The previous table draft proposed changing those behaviors. They are documented here as costing follow-ups, not silently presented as already implemented or added to this material-engine stage.

### Material valuation and customer PDF steps

| Step | Source / action | Calculation / check | Result |
| --- | --- | --- | --- |
| 1 — Generate materials | Selected package, inputs, templates and actual Item links | Evaluate conditions and quantity dependencies | A complete material snapshot; no partial replacement on formula errors. |
| 2 — Value materials | Company / warehouse stock valuation | Validate stock-to-row UOM conversion; amount = quantity × row-unit rate | Saved valuation estimate; unresolved rates / conversions are flagged. |
| 3 — Add current charges | Existing Project Cost Breakdown | project_cost = material_cost + other_cost | Keep existing charge defaults and formulas. |
| 4 — Apply current deductions | Existing discount and subsidy fields | final_amount = project_cost − discount − subsidy | The existing proposal price summary. |
| 5 — Review and print | Save → Print → Solar Proposal → PDF | Resolve formula and costing errors before final output | Customer system details, grouped material list, price summary and existing terms. |

Use valuation only: no silent standard-rate or buying-price fallback. Convert stock UOM rates into the material UOM; for arithmetic illustration, ₹100 per metre × 25 metres per roll gives ₹2,500 per roll. Missing conversion is an unresolved cost, not a conversion factor guessed as 1.

Empty templates and omitted workbook components remain editable. Formula errors prevent generation; missing valuation may remain in an incomplete draft but must be resolved before the customer PDF. Internal costs / margin rows do not need to appear in the customer PDF; existing Solar Proposal Content supplies warranty and terms.

