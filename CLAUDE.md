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

## Toolbar (systray) icons

- Every icon a module adds to the top toolbar must also show on the `/odoo`
  home screen, not only inside apps. `web_home_menu` hides toolbar icons on
  the home screen unless they opt in, so register them with
  `showOnHomeScreen: true`:
  `registry.category("systray").add(key, { Component, showOnHomeScreen: true }, { sequence })`.

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

## Organisation structure (Division / Business Unit / Location / Department)

Every **primary model** carries the four Organisation fields and follows the
same rules. A primary model is any model an app opens from its menus outside
that app's **Configuration** or **Settings** menu (option lists and setup
models are not primary). This applies to core Odoo apps and our own modules.

- `org_structure` adds the fields automatically to the primary models of
  every installed app (`org_structure/models/ir_model_fields.py`):
  `org_division_id`, `org_business_unit_id`, `org_location_id`,
  `org_department_id`, plus `org_show_*` flags. Don't define fields with
  these names yourself, and don't add a second set under other names.
- So a new model gets them as long as it is opened from the app's menus
  outside Configuration/Settings. Put option and setup models under the
  app's Configuration menu (see Choice fields) so they are left alone.
- A model that isn't opened from a menu but should still carry the fields:
  depend on `org_structure` and inherit `org.scope.mixin`.
- Forms: an **Organisation** section with the four fields is added
  automatically (before the notebook, or at the end of the sheet). Each
  field only shows when its level has units, and the section only shows
  once Divisions exist. To place it yourself, add the four fields in a
  `<group string="Organisation">` with `invisible="not org_show_<level>"`
  on each; the automatic section is then skipped.
- Picking a lower level fills in the levels above it; changing a higher
  level clears lower levels that don't belong to it.
- New records default to the logged-in user's Home Division / Business
  Unit / Location / Department, unless they come from a parent (below) or
  are given their own values. When only some levels are given, the missing
  higher levels come from the lowest given unit and lower ones stay empty
  (never a mix with the user's home units).
- Child records inherit from their parent: a record created with a parent
  (e.g. a Feed for an Enclosure, a Task for a Project) copies the parent's
  four values unless given its own. The parent is the first required
  Many2one to another Organisation-aware model, else the Many2one that is
  the inverse of the parent's One2many. When that isn't the right field, set
  `_org_parent_field = '<field>'` on the model (or `False` to turn it off).
- Record scoping (users' "Scope all apps" and App Specific Scoping) applies
  to these models automatically; records with no Division stay visible.
- Never scoped: technical and identity models (`ir.*`, `res.*` including
  `res.partner`/`res.users`, `mail.*`, `bus.*`, `org.*`), transient/abstract
  models and SQL views.
