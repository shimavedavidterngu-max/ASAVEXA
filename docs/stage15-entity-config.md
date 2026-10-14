# Stage 15: organisation type, subtype and workspaces in the menu

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack; no independent review. No production-readiness claim.

## What it does
- An organisation can say what **kind** it is (13 kinds, about 80 subtypes, from your expansion document: individuals, businesses, industries, firms, financial institutions, government bodies, nonprofits, faith bodies, education, health, essential services, assurance providers and regulators, funders), add a subtype, and describe itself **in its own words** (so the list is not a rigid hierarchy). It can also record languages and a time zone.
- It chooses **which workspaces appear in the menu**. Choosing a kind suggests a set; the person can tick or untick any workspace.
- Screen: **Organisation type and workspaces** (menu, under Data and administration; also reachable from the last set-up step). API: `GET /entity-config`, `GET /entity-config/catalog` (any member), `PUT /entity-config` (needs `org:manage_settings`).
- Every change is audited (`ENTITY_CONFIG_SAVED`), keeps its old values in a history, and needs a reason once the organisation has been set up. A save that changes nothing is refused.

## What it does NOT do
- **It does not grant or remove anyone's access.** Hiding a workspace removes a menu entry (and its global-search entry). A person with the permission can still open the page by its address, and the server checks the permission on every action as before. It is a convenience, not a security control.
- It does not pick an accounting or legal framework. Country, currency, fiscal-year start and reporting framework stay in the existing organisation profile.
- An organisation that has not been set up sees every workspace, exactly as before.
- Workspaces for the 27 professional groups in your expansion document do not exist yet; this stage is the foundation that lets them be switched on per organisation as they are built.

## Found and fixed while testing
- A workspace hidden from the menu showed "Page not found" in its breadcrumb. Breadcrumbs now use the full list of pages the person may open.
- My earlier audit said the organisation record had no country, currency, fiscal year or framework. That was too strong: the existing organisation profile holds all four. The real gaps were the fixed list of eight organisation types, no subtypes, and no per-organisation workspace choice.

## Design notes
- Stored in the shared document store (`ent_config`), one record per organisation, so there is no new database table or migration.
- Workspace ids come from `asavexa/workspaces.py`. A test fails if the catalogue and the menu paths drift apart, or if a kind suggests a workspace that does not exist. Workspaces added in later stages appear automatically in the checklist.
