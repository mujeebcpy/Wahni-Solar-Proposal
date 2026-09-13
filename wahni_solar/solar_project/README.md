# Solar Project

Project report generation lives in this module. It requires ERPNext, `wahni_kseb`,
and `pypdf>=6.13.3,<7`.

## Deployment

After installing the updated app and its Python dependencies in the target bench:

```sh
bench --site YOUR_SITE migrate
bench build --app wahni_solar
bench restart
```

Migration creates the Project fields and seeds the supplied documents as private
library attachments. It does not overwrite existing library records. A worker
serving the `long` queue must be running. The site's file size limit must accommodate
the combined report and its input archive; adjust it if generation reports a size error.

## Maintaining documents

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
attachment containing both the datasheet and BIS. Set **Panel Watt Peak (Wp)** in
the Project's Project Report section. The brand comes from its linked Solar Proposal.
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

Save the Project and click **Generate Project Report**. The latest generation and
its results are available on Project and in **Report History**. Inputs are captured
before queuing, so later library replacements cannot change a running generation.

Available PDFs are merged in the fixed order in `constants.py`, with PDF bookmarks.
Missing documents are listed. Missing optional cover/end pages and absent invoices
are silently skipped. If several submitted, non-return invoices match the Project
and customer, select **Report Sales Invoice**; otherwise that section is skipped.

Checklist and completion forms remain editable inside the merged PDF; they are not
saved or offered as separate generated attachments. Only available data replaces
form values. Fields with no available data retain their template values and defaults.
The customer Bank Account's Branch Code supplies IFSC. Downloaded edits do not update
ERPNext; an externally completed individual PDF can still be uploaded as a Project override.

Annexures are selected from the linked Grid Check's attachments, newest first. The
lookup accepts numeric/Roman annexure numbers, spaces, underscores, and filename
suffixes rather than requiring an exact generated filename. If an annexure has no
existing attachment or Project override, the existing KSEB generator creates it and
attaches it to the Grid Check before it is included in the report snapshot. Generation
requires Grid Check write permission and the same mandatory fields as its Annexure
buttons. A generation failure is listed as an omission without blocking other documents.

The generated QET drawing replaces customer/title-block properties; it does not
redesign the circuit or adjust wiring and equipment. Open it in QElectroTech, review
the drawing, export a PDF, and upload it as **Single Line Diagram**. Generation skips
that PDF section until an exported PDF is available.

The SLD plant connection type comes from the linked Solar Package's `connection_type`,
captured in the report snapshot. The Solar Proposal print format uses the same package
field. The Grid Check's `phase` supplies the customer supply phase in the SLD, checklist,
and completion certificate.

The QET location uses the customer's primary Address (or a sole/unambiguous linked
address), joining non-empty City and County values with `, `. Country is not used.
If no usable address values are available, it falls back to the KSEB address.

Input archives and output files are private. Report access follows Project read
permissions. Generation requires Project write permission and reads source documents
under the requesting user's permissions. Interrupted jobs can be regenerated.

System Managers and Projects Managers with access to the Project, and Administrator,
can delete finished or failed report records. Queued/running reports cannot be deleted.
Deleting the latest report restores the latest remaining generation on Project, or
clears the link if none remains. Generated PDFs and QET files already attached directly
to Project remain there; the report's input snapshot follows Frappe's attachment cleanup.

## Tests

Run with the bench environment's Python and this app on `PYTHONPATH`:

```sh
python -m unittest wahni_solar.solar_project.test_documents wahni_solar.solar_project.test_api wahni_solar.solar_project.test_permissions
```

These tests use the supplied PDFs/QETs and mocked Frappe storage. They do not need a
database or change site records. After migration, verify the Project button, worker
progress, file permissions, and the library replacement workflow on a test Project.
