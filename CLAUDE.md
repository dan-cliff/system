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

## AI functions

- Whenever anything we build calls an AI service (Claude, Gemini, ...), the user
  must see an in-progress overlay while it runs that tells them what the AI is
  doing - never just a button spinner or a screen that looks frozen.
- Start AI work from a JS widget (or client action), not a plain
  `type="object"` button: save the record first, show the overlay, call the
  server method with `orm.call`, then reload the record, show a success or
  error notification, and hide the overlay in a `finally`.
- The overlay lists the job's steps (e.g. Saving -> Checking what is needed ->
  Asking Claude to ... -> Updating the record), marks the one running, words
  the AI step specifically (what is being generated - fetch the details from
  the server first if needed, e.g. the names of the fields being filled in) and
  shows the elapsed time with "This can take a few minutes - please keep this
  page open".
- Render it as a full-screen `main_components` overlay so it sits above
  dialogs. Modules depending on `risk_management` reuse `aiProgress` from
  `@risk_management/ai_progress/ai_progress`; others follow the same pattern
  (the checklists AI generator overlay is another example).
- This also covers AI calls made as a side effect (e.g. on save): move them to
  an explicit action with the overlay, or run them in the background so they
  never block the user without explanation.

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

## Company

- Always show a Company field when multi-company is enabled. Every primary
  model (see Organisation structure below) has a `company_id`
  (`res.company`, defaulting to `self.env.company`) shown on its form and
  in its list (`optional="show"`), each with
  `groups="base.group_multi_company"` so it only appears when multi-company
  is on, plus a "Company" group-by in its search view (same `groups`).
- Give a model with `company_id` a multi-company `ir.rule`:
  `[('company_id', 'in', company_ids)]`.

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
- Settings › **Organisational Management** (`org.config`, stored as
  system parameters) can disable levels, relabel them (singular and plural)
  and choose which higher level each level sits under. Never hard-code a
  level's name or assume all four levels or the default parents:
  - read the configuration through `env['org.config']` (`_is_enabled`,
    `_label`, `_parent_level`, `_relabel`);
  - labels are applied on the fly to field strings (`fields_get`) and to
    the Organisation parts of views, so use the default names
    ("Division", "Business Units", …) in field strings and view text and
    let the relabelling replace them; the field names never change;
  - a disabled level's fields are hidden automatically; in your own views
    tag any wrapper of a level's fields with class `o_org_level_<level>`
    so it is hidden too.
- Forms: an **Organisation** section with the four fields is added
  automatically (before the notebook, or at the end of the sheet). Each
  field only shows when its level is enabled and has units, and the
  section only shows when at least one level does. To place it yourself,
  add the four fields in a `<group string="Organisation">` with
  `invisible="not org_show_<level>"` on each; the automatic section is
  then skipped.
- To put a model's Company field at the top of the automatic Organisation
  section, set `_org_form_company = True` on the model: its `company_id`
  field is moved there (for multi-company users the section then always
  shows).
- Org units store a link to every level above them; the configured parent
  is the editable, required one and the levels above it are derived.
  Picking a lower level on a record fills in the levels above it from the
  unit's links; changing a higher level clears lower levels that don't
  belong to it.
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
  to these models automatically; records with no Organisation units at all
  stay visible.
- Contacts (`res.partner`) are scoped too, whatever the menus. A contact
  under a company inherits the company's units (`parent_id`). Always
  visible to everyone: the user's own contact, every user's contact (users
  are built on contacts, so hiding one hides the user) and company
  contacts. A user's contact follows that user's home units.
- Never scoped: other technical and identity models (`ir.*`, `res.*` such
  as `res.users`/`res.company`, `mail.*`, `bus.*`, `org.*`),
  transient/abstract models and SQL views.

## Hardware on the local network (IoT Interfaces Nodes)

Odoo is hosted outside our network (Cloudpepper), so it can never connect
to hardware on the local network (machines, printers, screens, sensors),
and anything without a public internet API is out of its reach. Whenever we
build something that talks to such hardware, plan the interface through a
**Node**: a Raspberry Pi on the local network that connects out to Odoo.
Always call it a Node in code, views and docs.

- All Node configuration lives in the **IoT Interfaces** app
  (`iot_interfaces`): depend on it; never build a separate device, token
  or pairing model, and never open a port into the network or have Odoo
  call the hardware directly.
- Add a **role** for the program the Node runs:
  `role = fields.Selection(selection_add=[('<app>_<role>', '<Label>')],
  ondelete={...: 'set default'})` on `iot.node`. Put the role's settings
  (e.g. which machines a bridge serves) on `iot.node` with `_inherit`,
  shown in an inherited Node form page with `invisible="role != '...'"`,
  and add filtered Node menus under `iot_interfaces.menu_iot_nodes`.
- Authentication is always IoT Interfaces' rolling-key scheme: Nodes pair
  once with a one-time code, then every request is signed (HMAC-SHA256,
  timestamped, replay-proof), the key rotates automatically and authorised
  MAC addresses are enforced. In controllers, use
  `from odoo.addons.iot_interfaces.controllers.main import authenticate`
  and `node, error = authenticate(roles=['<role>'])` on every route
  (`auth='public'`, `csrf=False`, `save_session=False`). Never add bearer
  tokens, secrets in URLs or logins for Nodes.
- Ship the role's program in `<module>/node_programs/<role>/` with an
  `iot_program.json` (`entrypoint` the agent starts and supervises, `home`
  for screens, `setup` for a root setup script), register it in
  `iot.program._iot_builtin_programs()` and call
  `<function model="iot.program" name="_iot_sync_builtin"/>` in a data
  file. Programs reach Odoo only through the Node agent's local address
  (`$IOT_PROXY_URL`), which signs for them: programs never hold the key.
- Every Node is built with the same command
  (`curl -fsSL <odoo>/iot/install.sh | sudo bash -s -- --url <odoo> --pair <code>`)
  and takes program updates over the air, rolling back a version that keeps
  crashing. Changes to a program go out as a new program version (or a
  GitHub commit when GitHub is enabled in IoT Interfaces Settings), never by
  logging in to the Node. Only `setup` changes need the install command run
  again.

## ESM Measures inspections

Every inspection type in `esm_measures` (First Aid Kit `fak`, Emergency
Egress Door `eed`, Smoke Alarm `sma`, Evacuation Plan `evp`, …) is built
the same way. A new one copies an existing type's files with its own code
(`esm_<code>_template.py`, `esm_<code>_inspection.py` and their views) and
gets all of the following:

- Models: `esm.<code>.template` → questions → button values (with `color`),
  `esm.<code>.inspection` → `esm.<code>.inspection.line` (copied from the
  template's questions). The question type stays the shared
  `QUESTION_TYPES` selection.
- Company: the inspection has a required `company_id` (default the
  current company, tracked) on its form, as a list column and as a
  search field and Group By; the PDF logo and the asset filter use it.
- Chatter: the inspection model inherits `mail.thread` and
  `mail.activity.mixin`, tracks its main fields (`tracking=True`) and its
  form ends with `<chatter/>`. Templates, questions and button values have
  no chatter.
- Menus: the inspection under the app root, its template under
  Configuration; a Default Template setting in its own block on the
  ESM Measures settings page; an `ir.sequence` (`<CODE>/00001`); access
  rights in `security/ir.model.access.csv`.
- Checks on the form: the `line_ids` field uses
  `widget="esm_inspection_checks"` with `class="o_field_highlight"` and the
  `<kanban>` sub-view of the existing types (Buttons answers use
  `widget="esm_colour_badge"`).
- Template JSON export/import: the template model inherits
  `esm.template.mixin`; its form has the `action_export_json` header button,
  its list has the "Import JSON" header button (opening
  `action_esm_template_import_wizard` with `default_template_model`), and
  `data/esm_template_actions.xml` has its "Export JSON" server action.
- PDF: the line model inherits `esm.inspection.line.mixin`;
  `report/esm_inspection_report.xml` has its thin `report_esm_<code>_inspection`
  template (calling the shared `report_inspection`) and its
  `ir.actions.report` (report names must be unique per model); the form has
  the "Print PDF" header button.
- With Asset Management (`esm_measures_asset`): Visible Asset Types /
  Subtypes settings in its block (fields on `res.company`) and a filtered
  `asset_id` on the inspection, with `_org_parent_field = 'asset_id'`.
