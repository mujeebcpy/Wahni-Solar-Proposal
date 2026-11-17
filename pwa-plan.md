# Wahni Field PWA implementation plan

## Goal

Build a mobile-first employee portal inside `wahni_solar`, served at **`/field`**.
Employees should be able to record field work without navigating ERPNext Desk.
Use **Vue 3 and Frappe UI**, with the mobile interaction patterns of the HRMS PWA
at `/hrms`. Reuse or adapt its login, installation and expense-claim behaviour
without modifying HRMS itself.

The working app name is **Wahni Field**.

## Implementation status (2026-11-17)

Phases 0–4 are implemented on `erpbeta.wahni.in` (migrated after a backup) and
Phase 5 automated hardening checks pass. Real-device acceptance (Android Chrome,
iPhone Safari/standalone over HTTPS) and OTP/2FA/social login against configured
providers have **not** been performed; they remain release gates.

Decisions taken: office roles are System Manager and Projects Manager (Projects
Manager gained write/create on both visit DocTypes and may complete visits);
supervisor visibility is enforced everywhere, not only in `/field`; Completed
visits are locked for everyone except the office, which can reopen them; the
frontend is written for this app (HRMS UX patterns, no copied GPL source) on
frappe-ui 0.1.105 without Ionic.

Verified inside the container: 49 frontend unit tests; 36 portal integration
tests (access, portal, expenses, visits) plus the 14 existing Site Visit
integration tests; unit tests unchanged from baseline (8 pre-existing
solar_monitor/PDF failures are unrelated). Headless-Chrome E2E against the dev
server: 92 workflow checks (phases 1–4) and 32 hardening checks (320px layouts,
axe serious/critical = 0, offline, slow network/duplicate taps, oversized files,
location denial, worker update prompt).

Known limits: expense isolation in Desk relies on HRMS's Employee User
Permission (created automatically for employees with a linked user); the portal
itself always restricts to the session employee. Expense claims stay drafts for
the approver (no workflow is configured on this site; workflow transitions are
offered when one exists).

## 1. Scope

### First release

- Employee login, logout, profile summary and installation guidance.
- Expense Claim creation, draft editing, receipt uploads, permitted submission
  or workflow actions, and approval/payment status tracking.
- Site Visit creation, assigned-work lists, partial saves and completion.
- PMS Visit creation, assigned-work lists, inspection photos, partial saves and
  completion.
- Both admin-assigned visits and supervisor-created visits in the same lists.

### Not included

- Attendance, leave, payroll, salary slips or other HRMS modules.
- A mobile replacement for general ERPNext administration.
- Expense approval, accounting or payment processing screens.
- A separate employee-advance application; allocating existing advances within
  an expense claim may remain available when required by HRMS configuration.
- Full offline writes/background synchronisation, push notifications, route
  tracking or continuous location collection.

Admins continue planning and assigning visits in Desk. Supervisors use `/field`
to create their own visits or fill details on visits prepared by the office.

## 2. Completed DocType foundation

Implemented and migrated on `erpbeta.wahni.in` on 2026-11-17, following a database
backup. Other sites require their own normal site migration when deployed.

Both visit types now use:

```text
Assigned → In Progress → Completed
```

These are normal document statuses, not Frappe submission/docstatus transitions.

| Item | Current behaviour |
| --- | --- |
| Site Visit assignment | `site_visit_by`, linking to Employee |
| PMS Visit assignment | `service_person`, linking to Employee |
| Eligible assignee | Active Employee with an enabled User holding Project Supervisor |
| Site Visit source | Required Solar Proposal; one Site Visit per proposal |
| PMS Visit source | Completed Project for new visits; multiple visits per Project allowed |
| Incomplete records | Can be saved as Assigned or In Progress before collecting actual visit details |
| Site Visit completion | Requires actual Visit Date and Site Visit By, retaining existing server validation |
| PMS completion | Requires actual PMS Date, place, capacity, location link, required photos and remarks |
| Completion authorisation | System Manager or Project Supervisor, with assignee eligibility checked on completion |
| Existing history | Legacy PMS exceptions and unchanged historical employee links remain supported |

New Site Visits require an assignee. Existing unassigned Site Visits remain
editable so the office can assign them later. PMS retains its existing
Customer/Client Name and employee requirements for new records.

The migration converts Site Visit Draft to Assigned. Previously saved PMS
records with all completion fields become Completed; incomplete ones remain
Assigned. Report contents, attachments and modification timestamps are preserved.

Relevant existing code:

- `wahni_solar/site_visit/api.py`: proposal defaults, existing-visit lookup and
  supervisor eligibility/search.
- `wahni_solar/site_visit/doctype/site_visit/`: Site Visit schema and validation.
- `wahni_solar/site_visit/doctype/pms_visit/`: PMS schema, completed-Project defaults
  and validation.
- `wahni_solar/site_visit/migrate_visit_status.py`: lifecycle migration.

Session-based self-assignment, employee-only visibility, reassignment restrictions
and the office-only reopen policy are now implemented (see the status above).
Planned dates and office instructions are still not fields.

Foundation verification completed inside the Docker container: 61 unit/schema
tests, 14 site integration tests and 9 JavaScript form checks. Integration test
records were rolled back.

## 3. Assignment and access contract

### Access to the portal

Require an authenticated, enabled User linked to an active Employee and holding
the Project Supervisor role. Enforce the gate in protected server APIs as well
as frontend route guards. Show a useful access-denied or missing-Employee screen.

Resolve employee identity on the server. Do not trust an employee ID or role
provided by the browser, and do not infer assignment from document ownership.
An admin-created visit must belong in the assigned employee's list even though
its `owner` is the admin.

### Proposed employee visibility

- Expense Claims: the session employee's own records.
- Site Visits: `site_visit_by` equals the session employee.
- PMS Visits: `service_person` equals the session employee.
- Supervisors can create records for themselves; office users can assign and
  reassign within their authorised scope.
- Preserve explicitly authorised office access rather than blindly removing
  existing Sales User or Projects-role access.

Confirm the exact office roles and whether these visibility restrictions apply
throughout Desk and standard APIs before implementing them. The recommended
security boundary is server-side document/list enforcement for supervisors,
while retaining explicitly authorised office access. A PWA list filter alone
does not protect records reachable through standard Frappe APIs.

### Remaining backend work before exposing employee lists

- [x] Set assignment to the session Employee when a supervisor creates a visit.
- [x] Reject attempts by a supervisor to assign/reassign someone else's visit.
- [x] Apply the agreed record visibility to list, read, write and file access.
- [x] Permission-filter proposal, Project and other Link searches.
- [x] Return only source details needed for field work; assignment must not
      grant unrestricted access to Project accounts, HR records or customer data.
- [x] Preserve existing source-access checks or introduce explicitly scoped
      server helpers where assigned staff need a limited source snapshot.
- [x] Protect source/employee fields on office-prepared records; decide how an
      authorised office user corrects a mistaken assignment or Project.
- [x] Decide whether completed reports are editable or require an admin reopen;
      enforce the chosen rule on the server, not just with disabled controls.
- [x] Test mixed-role users and ensure alternate API paths cannot bypass policy.

The employee Link is assignment truth. Frappe Assign To/ToDo may later provide
notifications, but must not create a conflicting second assignment mechanism.
Reassignment should move work between employee lists without deleting its data.

## 4. Mobile application layout

Bottom navigation: **Home · Site Visits · PMS · Expenses**.
Profile, logout and installation help live in a header menu.

| Route | Screen |
| --- | --- |
| `/field` | Home, quick actions and recent work |
| `/field/login` | Login |
| `/field/site-visits` | Assigned, In Progress and Completed site visits |
| `/field/site-visits/new` | Create a self-assigned site visit |
| `/field/site-visits/:name` | Fill or review a site visit |
| `/field/pms-visits` | Assigned, In Progress and Completed PMS visits |
| `/field/pms-visits/new` | Create a self-assigned PMS visit |
| `/field/pms-visits/:name` | Fill or review a PMS visit |
| `/field/expenses` | Own claims and their statuses |
| `/field/expenses/new` | New expense claim |
| `/field/expenses/:name` | Edit a draft or view claim status |

### Design requirements

- Design for phones first, including narrow screens, safe areas and the on-screen
  keyboard; remain usable on tablets and desktops.
- Single-column layouts, card lists, persistent labels and at least 44px touch
  targets. Avoid horizontal scrolling and desktop child-table grids.
- Show customer names and useful source details, not only document IDs.
- Search, pagination, loading states, empty states and retryable errors.
- Sticky primary actions such as Save Progress and Complete Visit, without
  covering inputs or the keyboard.
- Numeric input keyboards for amounts and measurements; readable dates/currency.
- Clear unsaved/saving/saved/uploading indicators. Warn before discarding edits.
- Inline validation and navigation to the first field that needs attention.
- Screen-reader labels, visible focus, keyboard support and non-colour status cues.
- Preserve form values after validation/network failures. Detect concurrent Desk
  edits rather than silently overwriting newer data.
- Make all user-facing labels translatable; confirm additional language needs.

## 5. Employee workflows

### Site Visits

1. Open an assigned visit, or select New Visit and a permitted Solar Proposal.
2. Reuse existing-visit lookup: open the existing accessible report instead of
   creating a second report for the proposal. Do not reveal inaccessible reports.
3. Default the assignee for self-created visits and reuse proposal/customer
   snapshots. Preserve deliberate manual changes when loading defaults.
4. Present short sections: Customer, Location, Site Details, Measurements,
   Drawings and Review.
5. For office-prepared visits, show source/assignment context and move directly
   to the information the employee needs to collect.
6. Save partial work on the server as Assigned/In Progress.
7. Record the actual visit date and complete using existing server rules.

Support private drawings/sketches, attachment previews and optional tap-to-call
or directions when data exists. Optional GPS capture requires explicit browser
permission and manual-entry fallback; convert it to the existing Geolocation
field's expected format rather than storing an incompatible string.

### PMS Visits

1. Open an assigned visit, or select New Visit and a permitted completed Project.
2. Default the service person for self-created records and reuse Project/customer
   defaults. Preserve manually supplied capacity and valid Customer/Client choices.
3. Collect actual date, location, capacity, photos and inspection remarks.
4. Use labelled camera/gallery cards with capture guidance, previews, replacement,
   upload progress and retry. Keep mandatory and optional photo categories clear.
5. Save incomplete work on the server as Assigned/In Progress.
6. Review and complete only when all required data is present.

Required PMS photo categories are AC DB and String Inverter, Panel Image and
House Image. Keep the other existing image fields available as optional inputs.
Do not expose legacy import identifiers as editable fields.

### Expense Claims

Adapt the employee flow from HRMS, using the actual Expense Claim DocType:

1. Default employee, company, date, approver and applicable accounting details.
2. Add expense items using mobile cards/sheets: date, type, description and amount.
3. Upload private receipt photos/files and select a permitted Project if needed.
4. Review server-calculated totals and configured taxes, currencies or allocated
   advances. Do not show optional accounting complexity unless applicable.
5. Save a draft or perform the action permitted by the site's actual workflow.
6. View approval, rejection and payment status without mobile approval screens.

Retain HRMS validation, accounting and approval logic. Do not assume that a
generic Submit action is valid for every configured workflow, or that browser
totals/approval flags are authoritative. Do not allow claiming for another employee.

## 6. Frontend and Frappe architecture

Create a separately built frontend in this app; do not fork or edit HRMS to add
Wahni routes. Suggested structure:

```text
frontend/                         Vue application, tests and build configuration
  src/pages/                      Home, visits, PMS, expenses, authentication
  src/components/                 Mobile shell, fields, photos and list cards
  src/composables/                 Session, metadata and document interactions
  src/router/                     /field routes and access guards
wahni_solar/field_portal/          Protected APIs and portal access policy
wahni_solar/www/field.py           Minimal page context/boot data
wahni_solar/www/field.html         Built SPA entry
wahni_solar/public/field/          Generated frontend/PWA assets
```

- Register `/field` and nested SPA routes through `wahni_solar/hooks.py`.
- Separate asset URLs from router history URLs. Direct links and refresh must
  work on every `/field/...` screen.
- Use Frappe UI data APIs supported by the pinned version, Frappe sessions and
  CSRF handling. Do not store passwords or API secrets in browser storage.
- Call shared Python defaults/validation through narrow APIs. Save with normal
  document permissions and controllers; do not use `ignore_permissions` to make
  employee screens work.
- Treat upload, completion and workflow endpoints as permission boundaries.
- Reuse existing DocTypes; no portal-specific duplicate report/claim database.
- Add HRMS to the app dependency declaration or document/enforce its installation
  as an explicit portal prerequisite, since Expense Claim functionality needs it.

### HRMS reuse and version compatibility

At inspection, the bench had Frappe/ERPNext v16 and HRMS `17.0.0-dev`; the HRMS
frontend declared Frappe UI `0.1.105` and Ionic Vue. Recheck versions at build time.

Reuse/adapt the login/session, OTP, forgot-password, configured social-login,
install-prompt and expense interactions. Ionic may provide an HRMS-like mobile
shell if retained; Frappe UI provides the form controls and visual language.
Choose and pin one tested component/API generation before porting screens; do
not mix old HRMS component APIs with incompatible newer Frappe UI APIs.

Do not import private HRMS Vue source paths at runtime. Keep adapted components
in this app with clear provenance and tests against the installed HRMS APIs.
HRMS is GPLv3 while this app declares MIT: review licence compatibility and retain
required notices before directly copying/distributing HRMS source.

## 7. Metadata-driven forms and schema changes

Use a hybrid form layer: effective DocType metadata supplies field types, labels,
options and supported required/read-only/visibility conditions; explicit mobile
configuration supplies steps, special controls, Link filters and workflow actions.
Include Custom Fields and Property Setters, filtered for the user's field access.

Desk `frappe.ui.form.on` scripts do not run inside a Vue PWA. Reuse their shared
server helpers and deliberately implement required mobile interactions rather
than assuming Desk scripts will execute.

| Change | Expected effect |
| --- | --- |
| Label, description or supported Select options | Refresh metadata; usually no frontend rebuild |
| Supported simple field type change | Renderer can adapt; verify stored-data compatibility |
| New supported field | Map to a mobile section or supported Additional Details section |
| New mandatory field | Render/validate it and verify employee permissions/defaults |
| Rename/delete a field | Update field-name references, mappings, API contracts and tests |
| Link target/filter change | Review selector and backend permissions |
| New child table or unsupported field type | Add explicit component support |
| Workflow/business-rule change | Review actions, API behaviour and regression tests |
| Desk Client Script change | Not automatically inherited by the PWA |

Do not evaluate arbitrary dependency strings as JavaScript. Support a documented
safe subset or explicit conditions for the fields used here, with authoritative
server validation. Never silently omit an unsupported required field or expose a
hidden/restricted field. Metadata invalidation must account for deployments and
customisation changes; cached schemas cannot be treated as permanently valid.

The existing PMS controller's completion-field mapping is explicit Python logic.
Changing completion requirements therefore also requires reviewing that mapping
and its tests, even if the frontend renders the new metadata automatically.

## 8. Authentication, installation and connectivity

### Authentication

- Reuse the same-origin Frappe session: a valid existing login should not require
  another password entry solely to open `/field`.
- Support configured password/social login, OTP/2FA and password-reset flows.
  Preserve Frappe's security requirements; fall back to the standard login/setup
  flow where needed and return safely to the intended field route.
- Handle session expiry without pretending unsaved work reached the server.
- Restrict login return URLs and clear in-memory/sensitive client state on logout.

### Installable PWA

- Separate manifest identity, Wahni branding/icons, `start_url` and `/field/` scope.
- Canonicalise the entry route consistently and test standalone navigation.
- Android installation prompt when supported; iPhone Add to Home Screen guidance.
- Serve/register a worker with a deliberately correct `/field/` scope. If using
  `/field/sw.js`, serve that script explicitly instead of returning the SPA HTML.
- Keep worker registrations, cache names and navigation handling separate from
  `/hrms` and Desk. Test that both PWAs coexist on the same site.
- Cache versioned static assets only; do not service-worker-cache authenticated
  API responses, receipts, private images or session-specific boot HTML.
- Offer updates without force-reloading over unsaved edits. Use HTTPS in deployment.

### First-release connectivity policy

Online-first, with real server-side partial visit saves. An installed PWA does
not imply offline data entry/synchronisation is supported.

- Save visit progress as Assigned/In Progress and claims as permitted drafts.
- Show offline state and retain the current in-memory form on recoverable errors.
- Disable duplicate taps and handle uncertain write outcomes by refetching or
  reconciling before retrying, not blindly creating another record.
- Require connectivity for uploads, final saves, completion and claim submission.
- Implement authorised private uploads for new/partial records, attachment binding,
  cancellation and cleanup of abandoned uploads without deleting referenced files.
- Handle file size/type constraints, phone image orientation and supported formats;
  preserve enough image detail for readable component ratings and receipts.
- Defer persistent local drafts/photos unless a storage/privacy policy is agreed.
  If added, scope them by site/user, handle schema changes and clear them on logout.

## 9. Delivery phases and acceptance gates

### Phase 0 — Backend contract and permissions

The lifecycle foundation is complete. Finish the access/self-assignment work in
section 3 and agree office roles, completion edit policy and source visibility.
Verify assignments in Desk before exposing the portal. Add tests for forged
employee IDs, inaccessible sources, reassignment and direct API/file access.

### Phase 1 — Shell, login and installation

Build the pinned frontend, routing, Frappe boot/session integration, employee gate,
mobile navigation, manifest and scoped worker. Verify login/expiry/OTP and nested
route refresh; verify `/hrms` still works and installation is independent.

### Phase 2 — Expense claims

Adapt only the required HRMS components/APIs. Verify drafts, receipts, totals,
workflow submission and read-only statuses against configured HRMS behaviour.

### Phase 3 — Site Visits

Build assigned lists, self-creation, duplicate-proposal handling, stepped survey,
server progress saves, private drawings and completion. Verify that an admin-created
record appears for the assignee regardless of its owner.

### Phase 4 — PMS Visits

Build assigned lists, completed-Project selection, photo guidance, progress saves
and completion. Verify multiple visits per Project and preserved legacy history.

### Phase 5 — Mobile hardening and release

Test actual Android Chrome and iPhone Safari/standalone mode over HTTPS, narrow
screens, keyboard/safe-area behaviour, accessibility, large uploads, permission
denial, slow/interrupted networks, concurrent Desk edits and deployment updates.

Release only when employees can complete all three workflows without opening
Desk, and office users see the same underlying documents/files in ERPNext/HRMS.
Do not claim employee data isolation until negative permission tests pass through
standard APIs and file URLs as well as portal-specific endpoints.

## 10. Development and deployment

Follow `AGENTS.md`: source is host-mounted into the existing `frappe` container;
run Bench, Python, frontend builds and project checks inside that container.
Do not create a separate host bench or virtual environment.

From the Docker Compose directory:

```bash
docker compose exec -T frappe bash -c 'cd frappe-bench && bench version'
docker compose exec -T frappe bash -c 'cd frappe-bench && bench --site erpbeta.wahni.in backup'
docker compose exec -T frappe bash -c 'cd frappe-bench && bench --site erpbeta.wahni.in migrate'
docker compose exec -T frappe bash -c 'cd frappe-bench && bench --site erpbeta.wahni.in execute wahni_solar.site_visit.tests.test_integration.run'
```

`erpbeta.wahni.in` was explicitly selected for the completed foundation work.
Confirm the target before future site-specific deployments; do not migrate other
sites automatically. Add the frontend build to the app's normal asset pipeline
and document its exact build/test commands once the scaffold exists.

Keep backend unit/integration coverage, frontend component tests and end-to-end
mobile flows. Include schema-change tests to verify metadata refresh, conditional
requirements and clear handling of unsupported fields. Report exactly which
checks passed; browser/device acceptance remains separate from backend tests.
