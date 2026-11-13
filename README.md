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

#### Copy production Site Data Collection reports into PMS Visit

**Run on the production site, not the local development site.** Replace `<production-site>` below. Execute these commands inside that server's bench/container; for the local Docker layout, use the `docker compose exec -T frappe bash -c 'cd frappe-bench && ...'` wrapper documented above.

1. Put the site into maintenance mode and back up **both database and files**. Deploy this app version using your normal deployment process.

   ```bash
   bench --site <production-site> set-maintenance-mode on
   bench --site <production-site> backup --with-files
   bench --site <production-site> clear-cache
   bench --site <production-site> migrate
   ```

2. Preview the copy. This command makes **no changes**. Resolve any reported missing fields, missing image files, or conflicting names first.

   ```bash
   bench --site <production-site> execute wahni_solar.site_visit.migrate_pms.migrate --kwargs '{"dry_run": 1}'
   ```

3. If `errors` is empty, apply the copy, then preview again to verify `already_copied` matches `source_total`.

   ```bash
   bench --site <production-site> execute wahni_solar.site_visit.migrate_pms.migrate --kwargs '{"dry_run": 0}'
   bench --site <production-site> execute wahni_solar.site_visit.migrate_pms.migrate --kwargs '{"dry_run": 1}'
   ```

   The copy preserves original record names, Client Name, capacity, values, audit dates, and image URLs/privacy. It creates attachment references for PMS Visit without moving/deleting original files. **Historical copies may have no Project and remain editable without one**; no dummy Project is created. A protected migration reference distinguishes them from new reports. If a Project is linked later, it must be completed and cannot subsequently be cleared. Re-running skips already copied reports, never overwrites them, and does not delete or rename the source records/DocType.

4. Check several PMS reports and their photos. Switch any legacy Web Forms, Client Scripts, Print Formats, and menu links to PMS Visit as appropriate. Existing integrations referencing Site Data Collection are **not** rewritten automatically. Stop using the old entry form after verification to avoid parallel data entry; keep the source records as an archive until you decide otherwise.

   ```bash
   bench --site <production-site> clear-cache
   bench --site <production-site> set-maintenance-mode off
   ```

   Restart web/workers through your normal deployment process if required, then hard-refresh Desk. No production migration is run automatically by app installation or by `bench migrate`.

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
