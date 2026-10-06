# Solar Project

Project report generation lives in this module. It requires ERPNext, `wahni_kseb`,
and `pypdf>=6.13.3,<7`.

## Deployment

Deploy matching versions of `wahni_kseb` and `wahni_solar` and install their Python dependencies before migrating the target bench:

```sh
bench --site YOUR_SITE migrate
bench build --app wahni_kseb
bench build --app wahni_solar
bench restart
```

Migration creates the Project fields, four Project document DocTypes, seven print
formats, and the Project Documents workspace group. It seeds static library PDFs
and QET templates only; fillable templates are no longer seeded or selected.
Existing library records and historical files are preserved. A worker
serving the `long` queue must be running. The site's file size limit must accommodate
the combined report and its input archive; adjust it if generation reports a size error.

## Maintaining documents

### Equipment Items and package brands

Use the standard **Brand** field on Item. Items in the **Microinverters** group show
an optional **Model** field. Items in **Panel** show **Model** and **Watt Peak (Wp)**;
enter Wp manually for each panel Item. These fields use the exact item group names.
Changing groups hides the irrelevant fields without deleting their stored values.

Solar Package's **Brand** links to the Brand master and offers brands assigned to
enabled Microinverters Items that the user can access. Set the Brand on the Item
before choosing it on a new package. New/changed package brands are validated on
save. Existing packages keep their brand and remain editable while Item data is
being populated; migration creates missing Brand masters for those existing values.
Select **Panel Item** in the Project's Project Report section. The link offers only
Items in the **Panel** group, and report generation reads **Watt Peak (Wp)** from
that Item under the requesting user's read permissions. Migration removes the old
manual Project wattage field from the form while retaining its database values.
Existing Projects need a Panel Item selected before automatic panel document selection.

### Shared report documents

Open **Solar Project → Shared Report Documents**. Projects Managers, Sales Managers,
and System Managers can maintain the library.

- Upload optional **Cover Page** and **End Page** PDFs. All their pages are included.
- Replace a library record's Document attachment to update subsequent reports.
- Leave Equipment Brand blank for a common file; specify Enphase or Vsole for
  inverter documents and SLD templates, or the panel brand for panel documents.
  Combined panel datasheet/BIS records always require a brand and watt-peak.
- Equipment Model is an optional Item code matched against the Project Material
  List (falling back to the proposal BOM). A model match takes priority over a
  brand-only match; a brand match takes priority over a common file. The combined
  panel datasheet/BIS uses only brand + watt-peak, with no model or common fallback.
- Keep one enabled match at each specificity. Ambiguous matches are omitted with
  an explanation, rather than selected arbitrarily.
- PDF page ranges are inclusive and start at 1. Zero means the beginning/end.
  Inverter Datasheet and BIS records can share one uploaded file with different ranges.
- Checklist and completion templates must retain the named AcroForm fields from
  the supplied templates. New or renamed fields retain their template values unless mapped in code.

On Project, upload customer-specific PDFs in **Report Documents**, choosing their
categories. A Project upload overrides the automatic source, including cover/end
pages, annexures and manually completed forms. Replacing a Project attachment does
not alter previous generations.

For panels, create a **Project Report Document** with category **Panel Datasheet and BIS**,
Equipment Brand (e.g. `Adani`), **Panel Watt Peak (Wp)** (e.g. `630`), and one Document
attachment containing both the datasheet and BIS. Select **Panel Item** in
the Project's Project Report section and set **Watt Peak (Wp)** on that Item.
The brand comes from the linked Solar Proposal.
Both must match one enabled library record; `Adani / 600` and `Adani / 630` are separate
records. Brand matching ignores case and surrounding spaces. An ambiguous proposal
brand such as `Premier/Adani` does not choose either manufacturer's document.
Wp is the individual module rating, not the plant's total kW; it is not inferred from
capacity, panel count, or global default settings. Missing/ambiguous matches are listed
as omissions. A combined Project upload still takes precedence without requiring Wp.

The combined PDF is included once, after Project Completion Report and before Panel
DCR Certificate. DCR/warranty selection is unchanged. Existing separate Panel Datasheet
and Panel BIS records/uploads remain stored, but are no longer selected for new reports;
upload a combined replacement with brand and Wp and disable old library records.
The library form hides the old categories from new uploads. An existing legacy record
retains its current category until you change it; new separate panel records are rejected.
Previously queued snapshots finish using their original separate sections.

## Generating and editing

**Generate → Generate Project Report** automatically creates one record in each of
**Customer Vendor Agreement**, **Customer KSEB Agreement**, **Solar Installation
Checklist**, and **Solar Completion Certificate** for the Project. A required,
unique Project link and a Project row lock prevent duplicate records. Generation
reuses existing records and never resets saved edits or deliberately cleared defaults.

Each record stores only document-specific inputs. Customer names/addresses,
capacity, price, equipment, contacts, and bank details are resolved from the linked
records when printing. The form shows a read-only preview and links to those
sources. Correct shared information at its source; use the document form for
signatories, dates, declarations, serial numbers, settings, and measured readings.
Template choices/settings are editable defaults. Sample customer identities,
serials, and measured resistance values from the original PDFs are not defaults.
Agreement dates default on creation and are not recalculated when printing.

The **Solar Project → Project Documents** workspace group opens the four lists and
KSEB Grid Check. Project's dashboard and **Project Documents** menu open its forms.
No manual form preparation is required before report generation. Forms remain
editable and do not require submission.

Project's **Generate** menu provides SLD, both agreements, Check List, Project
Completion Report, and the complete report. Each PDF action selects its mapped
print format automatically and saves a private Project attachment. KSEB Grid
Check's Annexure I/II/III buttons save pending edits and render the corresponding
format as private Grid Check attachments. Native annexures use bundled Manjari
Regular/Bold fonts; no external font download is needed at print time.

Reports include fresh annexures, checklist, and completion certificate in the
existing section order, together with conditionally selected static uploads.
Agreements remain standalone. An explicitly selected Project Report Documents
upload takes precedence, allowing a signed or externally completed copy to be
included. Old Grid Check attachment filenames are no longer used to select an
annexure implicitly. A missing Grid Check is reported as an omission, not created.

Rendering uses Frappe's standard HTML/Jinja print pipeline. At generation time,
resolved values and rendered PDF bytes are frozen in the private report snapshot.
Later source/record edits affect future prints, not queued or historical reports.
The worker merges the frozen PDFs. Missing fields produce warnings with edit links;
existing mandatory annexure validation and partial-report handling are retained.

The consumer phase comes from Grid Check `phase`; plant connection type in the
SLD continues to come from Solar Package `connection_type`. Checklist/annexure
capacity comes from Grid Check; agreement capacity and cost come from Solar
Proposal. Customer address and equipment selection preserve the existing fallback
and ambiguity rules. Bank data is resolved only when permitted.

SLD generation still personalizes a QElectroTech `.qet` file. Open it in
QElectroTech, review/export the drawing as PDF, and select that PDF as the Project's
Single Line Diagram override. Its location continues to use the Customer Address
City/County, falling back to the KSEB address.

### Upgrade compatibility

Historical PDFs and explicit overrides are not rewritten or imported into new
DocTypes. All four records are created lazily on the next generation request.
Existing Grid Checks receive intentional static annexure defaults through a
one-time `wahni_kseb` patch; later edits/cleared values are never backfilled again.

Snapshots without `snapshot_version` retain their legacy worker behavior, so
already queued reports can finish. Form filling is retained only for these old
snapshots; version 2 snapshots do not call it. Drain all old queued jobs before
removing this compatibility branch in a future release. Keep `pypdf` for PDF
merging and proposal artwork processing.

Input archives and output files are private. Report access follows Project read
permissions. Generation requires Project write permission and reads source documents
under the requesting user's permissions. Interrupted jobs can be regenerated.

System Managers and Projects Managers with access to the Project, and Administrator,
can delete finished or failed report records. Queued/running reports cannot be deleted.
Deleting the latest report restores the latest remaining generation on Project, or
clears the link if none remains. Generated PDFs and QET files already attached directly
to Project remain there; the report's input snapshot follows Frappe's attachment cleanup.

## Tests

The unit tests live in `solar_project/tests/` and use Python's standard
`unittest.TestCase`, `setUp`, `subTest`, and `unittest.mock`. Test names describe
current behavior. Shared document doubles and template paths live in `helpers.py`.

Run from the app root (`apps/wahni_solar`) with the bench environment's Python:

```sh
python -m unittest discover -s wahni_solar/solar_project/tests -t . -v
```

To run one suite:

```sh
python -m unittest wahni_solar.solar_project.tests.test_generation -v
```

| Suite | Coverage |
| --- | --- |
| `test_documents.py` | Field mapping, legacy queued-snapshot form support, merging, SLD values |
| `test_sources.py` | Customer address fallback, Items, library selection, fresh annexures and overrides |
| `test_api.py` | Standalone actions, request permissions, duplicate requests, snapshots |
| `test_generation.py` | Report outputs, agreement exclusion, upload preservation, failures |
| `test_permissions.py` | Report deletion permissions and latest-report links |
| `test_equipment.py` | Brand search and package validation |
| `test_setup.py` | Repeatable setup that preserves existing library files and brands |

These tests exercise the supplied PDFs/QETs and mock Frappe storage. They require
the app's Frappe and pypdf dependencies, but no running site or database. They do
not change site records. Setup checks cover behavior still used on install/migrate;
obsolete field migrations and historical library compatibility checks are excluded.

After deployment, verify the Generate menu, actual worker progress, file permissions,
and library replacement workflow on a test Project. Those site/browser checks are
outside this unit suite.

Native document tests:

```sh
python -m unittest wahni_solar.solar_project.tests.test_project_documents -v
python -m unittest wahni_kseb.annexure.test_printing -v
```

On a staging site, run migration and generate a report twice from the same Project.
Confirm exactly four records exist, edit a default (including clearing it), and
regenerate. Change a source value and verify the next PDF changes while the earlier
report stays unchanged. Also check a restricted user's list/print access and a
signed Project override. These database/browser checks are separate from the
site-independent regression suite.
