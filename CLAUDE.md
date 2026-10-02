# CLAUDE.md

Custom Odoo 19 addons, deployed from `main` to system.cliffscountrycrafts.com
(Cloudpepper). Unless a request explicitly says otherwise, follow these rules
for every module we create or edit.

## Dates

- Show every date as **dd/mm/yyyy**, and timestamps as dd/mm/yyyy HH:MM
  (seconds optional).
- Odoo formats dates from the user's language: keep English on `%d/%m/%Y`
  (see `permission_management/data/res_lang_data.xml` and
  `zoo_manager/data/res_lang_data.xml`).
- Odoo 19 shows date/datetime fields as text ("Sep 27") unless the view asks
  for numbers: give every Date/Datetime `<field>` in form and list views
  `options="{'numeric': True}"` (merge into any existing options).
- Anywhere dates are formatted in code (`strftime`, record names, messages,
  reports, exports, emails), use `%d/%m/%Y` / `%d/%m/%Y %H:%M`, never
  `%Y-%m-%d` or `%m/%d/%Y`.
- Store dates as Odoo `Date` / `Datetime` fields, never as text.

## Choice fields

- Don't use `fields.Selection` for a list of choices. Use a `Many2one` (single
  choice) or `Many2many` (several choices) to a small model that holds the
  options.
- Each of those option models gets its own list/form views and a menu item
  under that app's **Configuration** menu, so users can add, rename and
  archive options themselves. Give them an `active` field, and a `sequence`
  field when order matters.
- Ship the starting options as `noupdate="1"` data, and give access rights
  (read for users, full for the app's administrators).
- Exceptions: technical states that code depends on (e.g. a record's workflow
  `state`), or when a request explicitly asks for a fixed selection.

## Access rights

- Every model gets its own access levels, not app-wide User/Manager groups:
  one privilege per model (named after it, e.g. "Risk Templates") holding
  **View Only**, **Create**, **Create and Edit Own Only**, **Update** and
  **Delete** groups, so they read "Risk Templates / Create".
- Declare them in the module's `access_levels.py` (format in
  `permission_management/access_levels_lib.py`): each model's kind
  (operational, configuration or Settings app) and the user fields that make
  a record "own". Then run `python3 tools/generate_access_levels.py <module>`
  (writes `security/access_levels.xml`, `security/ir.model.access.csv` and
  `data/access_roles.xml`) and `python3 tools/apply_menu_groups.py <module>`.
  Don't hand-edit the generated files.
- Roles: Administrator, Manager, Employee and View Only. Models on a
  Configuration/Settings menu or in the Settings app go in the Administrator
  role only (internal users can still read configuration lists). Employees get
  Create and Edit Own Only unless the app needs otherwise (override `ROLES`).
- Permission Management builds the roles from `access_levels.py` whenever
  either app is installed or upgraded.
- Record rules that must combine with Create and Edit Own Only (e.g.
  multi-company) are global (no `groups`); group rules are OR-ed and would
  lift the restriction.
- Moving a module to access levels: map its old groups to the new roles in a
  migration with `access_levels_lib.migrate_old_groups`.
