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
- New reports start as **Assigned** and require **Site Visit By**. Office staff can save the proposal and supervisor before the actual Visit Date or technical details are available. Supervisors can save partial work as **In Progress**, then mark it **Completed**. Existing unassigned reports remain editable so office staff can assign them later.
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

PMS uses **Assigned → In Progress → Completed**, defaulting to **Assigned**. Office staff can save an assignment with only its completed Project, supervisor, and Customer/Client Name. The actual PMS Date, place, capacity, location link, three required inspection photos, and inspection remarks are required only at completion; partial work can be saved on the server. Completion is restricted to System Managers, Projects Managers and Project Supervisors and rechecks the assigned Employee's eligibility. These rules are enforced in Python as well as the form metadata.

The normal site migration converts Site Visit **Draft** statuses to **Assigned**. Existing PMS reports with all completion fields are marked **Completed**; incomplete reports stay **Assigned**. It preserves report contents, files, assignments and modification timestamps. The employee links, not document ownership or Frappe ToDos, identify the supervisor's work lists (see **Visit access** below).

Document-level roles match Site Visit: System Manager, Projects Manager, Sales User, and Project Supervisor can create/edit; Projects User can read. Users must also have normal permission to select the linked Project (for example, Projects User or another applicable ERPNext role). No ERPNext Project permissions are broadened automatically.

#### Visit access

Enforced on the server for Desk, REST APIs, file URLs and `/field` (`wahni_solar/field_portal/access.py`):

- **Office** users (System Manager, Projects Manager) see every Site/PMS Visit, can assign or reassign it to any eligible Employee, and are the only users who can edit or reopen a **Completed** visit (set it back to In Progress).
- A **Project Supervisor without an office role** sees only visits whose Site Visit By / Service Person is their own active Employee, regardless of who created them. Visits they create are assigned to themselves; they cannot reassign a visit or change a PMS visit's Project. Private files attached to a visit follow the same access.
- Other roles (e.g. Sales User, Projects User) keep their existing access, except that only the office can change Completed visits.
- Supervisors cannot read Solar Proposals; when creating a Site Visit they can search proposals without a visit (name and customer only), and the visit receives the usual snapshot fields.

#### Existing UAT reports

The one-time development/UAT patches and Site Data Collection copy command have been retired. Fresh installations use the standard PMS Visit schema and need no legacy data-copy step.

Reports already copied on UAT retain their names, values and photos and remain editable without a Project or Employee. Their hidden, immutable `legacy_site_data_collection` reference is retained only for compatibility; new visits cannot set it. If a Project is assigned later, it must be completed and cannot subsequently be cleared. No existing records, files or backup archives are deleted by this code cleanup.

### Wahni Field PWA (`/field`)

A mobile-first portal for field staff: Site Visits, PMS Visits and Expense Claims, installable as a PWA. Access needs an enabled User with the **Project Supervisor** role linked to an active Employee. Expense claims need **HRMS** (the portal reports this if it is missing; HRMS is not added to `required_apps`). Claims are saved as drafts for the Employee's expense approver; HRMS's own approval and accounting rules apply.

- Source: `frontend/` (Vue 3, frappe-ui 0.1.105, Vite, vite-plugin-pwa). APIs: `wahni_solar/field_portal/`. Entry page: `wahni_solar/www/field.py`; `www/field.html` and `public/field/` are generated by the build and ignored by git.
- `bench build` runs the app's root `package.json` build (`yarn build` in `frontend/`). The worker is served at `/field/sw.js` with `Service-Worker-Allowed: /field/` and only precaches versioned static assets; API responses, HTML and private files are never cached. Updates are offered in the app and are blocked while a form has unsaved changes.
- The portal is online-first: work is saved on the server (visits as Assigned/In Progress, claims as drafts). It does not store data offline.
- Visit forms are built from the effective DocType metadata (custom fields, property setters, permlevels). Label/option/hidden changes need no rebuild; new sections appear under **Additional Details**; unsupported field types are shown as "edit in Desk". `depends_on`/`mandatory_depends_on` support a documented safe subset (`frontend/src/utils/conditions.js`) and are never evaluated as JavaScript; the server remains authoritative. Steps and protected fields are configured in `VISIT_CONFIG` (`field_portal/visits.py`) and `frontend/src/utils/visitTypes.js`.

Build and checks (from the Compose directory; site tests roll back their records):

```bash
docker compose exec -T frappe bash -c 'cd frappe-bench/apps/wahni_solar/frontend && yarn install --frozen-lockfile && yarn test && yarn build'
docker compose exec -T frappe bash -c 'cd frappe-bench && for m in test_access_integration test_portal_integration test_expenses_integration test_visits_integration; do bench --site <site> execute wahni_solar.field_portal.tests.$m.run; done'
```

`wahni_solar.field_portal.tests.e2e_fixtures` creates **committed** test users and records for browser checks on a development site; always run its `teardown` afterwards.

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
