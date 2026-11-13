### Wahni Solar Proposal

App to autogenerate Solar Proposals based on user input basic data

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app wahni_solar
```

### Site Visits

- On a saved Solar Proposal, use **Create → Site Visit**, or add a report from the Site Visit list and select its proposal. Each proposal has one editable report; the action opens the existing report when present.
- Lead/Customer details and requested capacity are copied initially. Later edits to the report are preserved.
- Assign **Project Supervisor** to the User linked to an active Employee to make that Employee selectable in **Site Visit By**. The role is installed by the app but is not assigned automatically.
- Sales Users can prepare reports. Project Supervisors can edit technical findings, upload private layout drawings, and mark visits **Completed** once Visit Date and Site Visit By are entered.
- **Create → Project** warns when the visit is missing or incomplete but does not block creation. Existing visits are linked regardless of status; a visit created later is linked when the proposal-linked Project is next saved.
- **Site Visit** has its own map-pin dock icon and sidebar, separate from Solar Proposal, containing Site Visit reports and PMS Visits. Proposal **Create → Site Visit** remains available.

The workspace is named **Site Visits** (`/desk/site-visits`) so it does not shadow the DocType list (`/desk/site-visit/view/list`). Monitoring DocTypes belong to **Wahni Solar Monitor**, separate from Masters Association's module; existing `wahni_solar.solar_monitor` API and scheduled-job paths are unchanged.

For an existing Docker site, run from the Compose directory described in `AGENTS.md`:

```bash
docker compose exec -T frappe bash -c 'cd frappe-bench && bench --site <site> clear-cache && bench --site <site> migrate'
```

Site-independent checks and site integration checks (test records are rolled back):

```bash
docker compose exec -T frappe bash -c 'cd frappe-bench && env/bin/python -m unittest wahni_solar.site_visit.doctype.site_visit.test_site_visit'
docker compose exec -T frappe bash -c 'cd frappe-bench && bench --site <site> execute wahni_solar.site_visit.tests.test_integration.run'
```

### PMS Visits

Open **Site Visit → PMS Visits**. New reports require a **completed Project**. Selecting it fills **Customer** and the retained **Client Name** from the Project's Customer. Customer appears first; Client Name is shown and required only when no Customer is selected. Either a Customer or a manually entered Client Name is accepted, including for completed Projects without a Customer. Capacity stays editable and is not overwritten by Project selection. Multiple maintenance visits can be recorded for a Project.

**Service Person Name** links to an active Employee whose enabled User has the **Project Supervisor** role, using the same Employee filter as Site Visit. New reports must select an eligible Employee. Historical service-person text remains in `service_person_name`, so copied and pre-existing reports stay editable without matching old names to Employees. Once an Employee is assigned, it cannot be cleared; unchanged historical assignments remain valid if eligibility later changes. The original `client_name`, `plant_capacity_kw`, service-person, location, remarks, and seven image field names are retained.

Document-level roles match Site Visit: System Manager, Sales User, and Project Supervisor can create/edit; Projects User/Manager can read. Users must also have normal permission to select the linked Project (for example, Projects User or another applicable ERPNext role). No ERPNext Project permissions are broadened automatically.

#### Existing UAT reports

The one-time development/UAT patches and Site Data Collection copy command have been retired. Fresh installations use the standard PMS Visit schema and need no legacy data-copy step.

Reports already copied on UAT retain their names, values and photos and remain editable without a Project or Employee. Their hidden, immutable `legacy_site_data_collection` reference is retained only for compatibility; new visits cannot set it. If a Project is assigned later, it must be completed and cannot subsequently be cleared. No existing records, files or backup archives are deleted by this code cleanup.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/wahni_solar
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
