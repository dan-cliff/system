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
