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

## List views

- Every list view starts with the record ID: make
  `<field name="id" optional="show"/>` the first column, before any other
  field (a `handle` widget for `sequence` may sit in front of it).

## Reports menu (Report Builder)

Every app has a **Reports** menu where Report Builder (`report_builder`)
saves the app's custom reports.

- Add it to the app's root menu as a plain folder: no action, no `groups`,
  e.g. `<menuitem id="menu_<app>_reports" name="Reports"
  parent="menu_<app>_root" sequence="..."/>`. Don't depend on
  `report_builder` for it.
- It must only show when it holds reports. Odoo already hides a menu that
  has no action and no visible children, so the folder stays invisible
  until Report Builder places a report under it (it can only get reports
  once Report Builder is installed). Never give it an action, a
  placeholder child or an empty-state page, as that would make it show
  while empty.
- Place it last, directly before the app's **Configuration** / **Settings**
  menu (give it a sequence between the menu before it and Configuration).
  If the app has no Configuration or Settings menu, make it the app's last
  menu.
- It is separate from any built-in **Reporting** menu (analysis views) the
  app already has; keep both.

## Permissions (privileges and roles)

Every app gets the same access model, so Permission Management can build
roles from it.

- **Per-model privileges.** Each primary model (see Organisation structure)
  gets these privileges, each its own `res.groups.privilege` under the app's
  `ir.module.category`, named `<Records>: <Permission>` (e.g.
  "SCORM Courses: Delete Own"), with one group named "Allowed":

  | Permission | Gives |
  | --- | --- |
  | Create Only | create, and view their own (no editing after saving) |
  | Create and Edit Own | create, view and edit their own |
  | Create and Edit My Team | create, view and edit their own and their team's |
  | Create and Edit All | create, view and edit all |
  | View All | view all |
  | Delete Own | delete their own |
  | Delete All | delete all |

  - *Own* = records they created (`create_uid`), or that name them in the
    model's owner field (e.g. `user_id`) when it has one.
  - *My Team* = their own plus those of users whose employee sits under
    theirs in the org chart:
    `('create_uid.employee_ids', 'child_of', user.employee_ids.ids)`.
  - The meaning lives in `ir.rule`s on each "Allowed" group. Child models
    (lines, slides, comments, …) get the same rules through the path to
    their parent (e.g. `course_id.create_uid`), so access to a parent
    covers its children.
  - Each "Allowed" group implies the app's base user group (technical, no
    privilege). That base group has the ACL (`ir.model.access.csv`) on the
    app's models, plus a deny rule (`[(0, '=', 1)]`) for each of read,
    write, create and delete. Rules of different groups are OR-ed, so
    without a permission the user can do nothing, and each permission only
    opens what it names. Never grant access through the ACL alone.
  - Workflow actions that aren't CRUD (approve, publish, review, …) get
    their own privilege with an "Allowed" group. Check it in code with
    `has_group` before the action, and let the action write with `sudo()`.
  - Option models under Configuration keep simple ACLs: read for the app's
    users, full for the app's Administrator.
- **App Administrator group.** The app's privilege (named after the app)
  holds an "Administrator" group that implies every permission above
  (including the workflow ones) and gives Configuration access.
  `base.user_root` and `base.user_admin` are members.
- **Standard roles.** Each app ships three `permission.role` records in a
  bridge module `<app>_permission` (`depends: [<app>,
  'permission_management']`, `auto_install: True`; see
  `checklists_permission`), named `<App> – <Role>`:
  - **Administrator**: everything, including Delete All and every workflow
    privilege, plus the app's Administrator group.
  - **Manager**: Create and Edit My Team on every primary model, no delete.
  - **Employee**: Create and Edit Own on every primary model, no delete.

  Add app-specific roles (e.g. Reviewer, Approver) to the same file when
  the app has workflow privileges. Ship roles as `noupdate="1"` data so
  admins can adjust them.

## Icon style

Every icon we create (app icons in `static/description/icon.png`, menu
`web_icon`s, toolbar icons, pictures in empty-state help, illustrations)
follows the samples in `docs/icon_style/`. Look at them before drawing an
icon.

Always:

- **Transparent background.** No white, coloured or checkered square
  behind the icon. The checkerboard in some samples only shows
  transparency; it is not part of the icon. The only filled shape allowed
  is the rounded tile of the tile style itself.
- **No text.** No words, letters, numbers or logos. Use placeholder bars
  where text would be.
- **Stylised and abstract.** Simple geometric shapes that suggest the
  subject (people as a circle and a rounded body, a truck as blocks), never
  realistic drawings, photos, clip-art or detailed line art.
- **The standard colours below.** Don't bring in new hues. Vary only the
  shade and gradient within the palette.

The palette:

- coral/red `#FF5A6E` (soft pink `#F9A3A3` for secondary figures);
- yellow to orange `#FFC93C`→`#FF9F1C`;
- sky to royal blue `#3BB8FF`→`#0A6CF0`;
- teal/green `#14C9A5` (deep teal `#14A3A3`);
- purple/violet `#8E5CF0`→`#5B3DB8`, plum `#8E2F7A`;
- navy `#2A3F8F` for heavy parts;
- lavender-grey `#A9ABDC` for "text" bars;
- near-white `#F2F2FA` for panels and white `#FFFFFF` for glyphs and ticks.

The samples show three styles, all in the same family.

- **Illustrated** (the default for app icons):
  `sample_dashboard.webp`, `sample_checklist_alert.webp`,
  `sample_logistics_flat.webp`.
  - One main object that says what the app is (a browser window with
    charts, a clipboard with ticks or check boxes).
  - A second accent object overlapping its lower right corner for the
    app's twist (a pie chart, a warning beacon, a truck and forklift in a
    box).
  - Rounded corners everywhere and no hard black outlines.
  - Either soft, glossy "clay" shading (gentle gradients, a highlight on
    top, a soft shadow below) or flat colour blocks with simple faceted
    shading (a darker side and a lighter side on 3D shapes, as in the
    logistics sample).
  - The subject is centred and fills about 80% of the square.
- **Tile** (for when a flat tile suits better, e.g. small toolbar or menu
  icons): `sample_app_tile.webp`, `sample_healthcare_tile.webp`.
  - A rounded square with a diagonal gradient from violet `#B65CCB` /
    purple `#5B2E9E` (top left) to teal `#14A3A3` (bottom right),
    optionally split into faceted panels.
  - One or two bold glyphs in white and soft pink (people, a heart with a
    cross, an exit door). A glyph overlapping another is separated by a
    gap in the tile colour.
  - Everything outside the rounded square is transparent.
- **Small faceted mark** (for tiny sizes, e.g. 16 to 50 px):
  `sample_small_facets.png`.
  - A single angular shape made of two or three flat triangular facets in
    blue, violet and pink, on a transparent background.

Keep every icon in one family: the same palette, corner radius and lighting
across our apps. Never use Font Awesome glyphs, stock clip-art or Odoo's flat
default icons as an app icon.

Size and format:

- App icons are square PNGs with a transparent background (alpha channel),
  256×256 or larger (1024×1024 preferred), at
  `static/description/icon.png`, also used as the root menu's `web_icon`.
- Draw them as SVG and export the PNG, keeping the SVG next to it
  (`icon.svg`) so the icon can be changed later. Check the exported PNG
  really has transparent corners.

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
  `@risk_management/ai_progress/ai_progress`, and modules depending on
  `dev_management` reuse `dev.ai.mixin` with the `dev_ai_action` widget
  (`@dev_management/ai_progress/ai_progress`); others follow the same pattern
  (the checklists AI generator overlay is another example).
- This also covers AI calls made as a side effect (e.g. on save): move them to
  an explicit action with the overlay, or run them in the background so they
  never block the user without explanation.

### AI keys

Every AI feature is switched on only when at least one AI key is set, and the
app must keep working without one.

- Find the key in this order, preferring Claude/Anthropic and falling back
  to Google Gemini: the Claude key in Settings › General Settings ›
  Integrations (`claude_ai_settings.api_key`), the Anthropic key of the Odoo
  AI app (`ai.anthropic_key`), the Gemini key in General Settings
  (`claude_ai_settings.gemini_api_key`), then the Google key of the Odoo AI
  app (`ai.google_key`). The first key found picks the provider.
- Read these system parameters directly. Don't depend on
  `claude_ai_settings` or the Odoo AI app (`ai`) just to get a key, so the
  app installs and works when neither is installed.
- Handle having no AI gracefully, whether no AI app is installed or no key is
  set:
  - hide the AI buttons (an `ai_available` compute, with
    `invisible="not ai_available"` on the widget);
  - skip background AI jobs silently and fall back to the non-AI behaviour
    (e.g. a release keeps its number as its name);
  - show a note where the AI would be configured (e.g. next to the app's AI
    settings) saying where to add a key;
  - make any direct call raise a friendly `UserError` that says where to add
    a key, never a traceback.
- `dev_management/models/dev_ai.py` implements this (`ai_credentials`,
  `dev.ai._available()`); reuse it in modules that depend on
  `dev_management`, and copy it elsewhere.

## Actions (Actions app)

Every action, task or follow-up an app raises (corrective actions, actions
on risks, …) is stored in the **Actions** app's common model,
`advanced.action` (module `advanced_actions`), never in an actions model of
the app's own. Incidents, Risk Management, Injury Management, Zoo Manager and
Checklists already do (`advanced_actions_incident`, `advanced_actions_risk`,
`advanced_actions_injury`, `advanced_actions_zoo`; Checklists is built into
`advanced_actions`).

An action has a Title (`name`), Description, Assigned To (`user_ids`,
Many2many: any one of them can complete it), Due At (`date_deadline`,
Datetime), Status (`state`: open / in_progress / done / cancelled, a
statusbar), Created By / Created At, a Required Checklist
(`checklist_template_id`; completing the checklist completes the action) and
chatter. "Duplicate for Users" gives several users an action each.

When an app needs actions and Actions is installed, add a bridge module
`advanced_actions_<app>` (`depends: [<app>, 'advanced_actions']`,
`auto_install: True`; copy `advanced_actions_zoo`, or
`advanced_actions_incident` when moving an existing model's records):

- On `advanced.action`: a Many2one to the app's record (e.g.
  `incident_id`, `ondelete='cascade'`), the app in `source_app`
  (`selection_add=[('<app>', '<App>')], ondelete={'<app>': 'set default'}`)
  and the link in `_action_sources()` (`super() + [('<field>', '<app>')]`),
  so the action's App, Company and Organisation follow that record. Add
  app-specific fields there too (e.g. Incidents' Control Type).
- On the app's record: `action_ids = fields.One2many('advanced.action',
  '<field>')` and an Actions stat button or tab.
- The app's own **Actions** menu opens `advanced.action` filtered to the app
  by default, with the filter removable to show every action: add
  `<filter name="app_<app>" domain="[('source_app', '=', '<app>')]"/>` to
  the Actions search view (after `app_checklists`) and give the menu's
  window action `context="{'search_default_app_<app>': 1,
  'search_default_open': 1, 'default_source_app': '<app>'}"` and, if useful,
  a `mode="primary"` list view with the app's columns.
- Access: give the app's groups the ACL on `advanced.action` they had on
  their records, plus `ir.rule`s limited to the app's actions that follow the
  parent record's rules (e.g. `[('incident_id', '!=', False), …]`, or
  `[('source_app', '=', '<app>')]` when the parent has none). The Actions app
  denies everything else.
- Never send action emails from the app. Actions sends its Notification
  Templates, or Workflow Automation does when it is installed.
- Without Actions installed, an app either has no actions or keeps a simple
  model of its own. The bridge moves those records into Actions on install
  (`advanced.action._transfer_records` in a `post_init_hook`) and back in an
  `uninstall_hook`.

## Customers and contacts (Advanced Accounts)

Customers, vendors and the people we deal with are **Accounts**
(`advanced.account`, companies) and **Contacts** (`advanced.contact`, people
linked to an Account) from the **Advanced Accounts** app
(`advanced_accounts`), not the standard Contacts app. Both keep their
details on a `res.partner` (`_inherits`), and a user made for a Contact is
built on that same partner, so they stay in sync. Our own users and
employees are never Contacts: fields meant to pick an employee or user stay
as they are.

Whenever an app we create or update has a customer, vendor or contact
field (or should have one):

- Put the change in an optional support app `advanced_accounts_<app>`
  named "Remap <App> Contacts to Advanced Accounts" (`depends:
  ['advanced_accounts', '<app>']`, **not** `auto_install`), and add its
  `module_advanced_accounts_<app>` toggle to the Advanced Accounts settings
  page (`advanced_accounts/models/res_config_settings.py` and
  `views/res_config_settings_views.xml`), so each app is switched on by
  choice. The app itself keeps its `res.partner` field and works without
  Advanced Accounts.
- One customer per record: inherit `advanced.accounts.mixin`, which adds
  `adv_account_id` and `adv_contact_id`. Set `_adv_partner_field` to the
  partner field they stand in for (`False` when the record has none: the
  fields are then its own), and `_adv_account_partner_field` when the
  record keeps the Account in a separate partner field (see
  `advanced_accounts_crm`). Several partner fields, or ones that aren't
  "the customer" (e.g. an asset's Supplier, Manufacturer, Owner): inherit
  `advanced.accounts.remap.mixin` and list `{new field: partner field}` in
  `_adv_remap` (see `advanced_accounts_asset`).
- Views: put the Account and Contact fields just before the partner field,
  with the same `readonly` / `invisible` conditions, and make the partner
  field `invisible="adv_account_id or adv_contact_id or not partner_id"`
  (it then only shows for a partner that isn't an Account or Contact, such
  as one of our users). Lists: Account and Contact columns before the
  partner column, which becomes `optional="hide"`. Searches: the two
  fields and an "Account" group-by.
- Behaviour comes from the mixins: picking an Account limits the Contacts
  to that Account; picking a Contact fills in its Account; the Contact
  picker lists "Contact Name (Account Name)" while the chosen Contact
  shows its name only; the partner field follows, and partners made by
  other code join Advanced Accounts automatically.
- Need a login for a Contact? Use the Contact's "Create User" (a portal
  user on the Contact's partner), never a separate partner.

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
