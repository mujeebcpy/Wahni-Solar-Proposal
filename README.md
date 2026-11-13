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
- **Site Visit** has its own map-pin dock icon and sidebar, separate from Solar Proposal. This module will also host future preventive-maintenance visits; PMS is not implemented yet. Proposal **Create → Site Visit** remains available.

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
