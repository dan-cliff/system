"""Shared logic for per-model access levels.

A module opts in by shipping an ``access_levels.py`` (plain data, no Odoo imports) with:

* ``APP_NAME``: shown in role names, e.g. "Asset Management – Manager".
* ``PREFIX``: XML ID prefix; privileges are ``privilege_<PREFIX>_<key>`` and groups
  ``group_<PREFIX>_<key>_<permission>``.
* ``CATEGORY``: XML ID of the ``ir.module.category`` the privileges belong to (created by
  the generated security file when it has no module prefix).
* ``MODELS``: ``(key, label, kind, model_xmlids, own_fields)`` per model:
    - ``label`` names the privilege, so groups read "<label> / Create" etc.
    - ``kind`` is OPERATIONAL, CONFIG (on a Configuration menu) or SETTINGS (in the
      Settings app). CONFIG and SETTINGS models only go into the Administrator role;
      CONFIG models stay readable to every internal user so the records using them
      still display.
    - ``model_xmlids`` are the ``ir.model`` XML IDs (``model_x_y``) the groups grant
      access to (a model and its lines can share one set of groups).
    - ``own_fields`` are res.users fields (dotted paths allowed) that, besides
      ``create_uid``, make a record "own" for Create and Edit Own Only. Add
      ``'-create_uid'`` for models without that column (SQL views).
* Optional ``ROLES``: ``{role name: (description, {key: permissions})}`` replacing the
  default Administrator / Manager / Employee / View Only roles.
* Optional ``ROLE_EXTRA_GROUPS``: ``{role name: [group XML IDs]}`` added to those roles
  on top of their model groups (e.g. a feature group such as a confidentiality bypass).
* Optional ``EXTRA_ACCESS``: ``(id, model_xmlid, group_xmlid or '', 'rwcu')`` rows for
  wizards and technical models, written to ir.model.access.csv as they are.

Each model gets five groups. Create, Update and Delete imply View Only.
Create and Edit Own Only can create and edit, but only sees records the user created or
is named on (``own_fields``), unless the user also has Update or Delete on that model.
"""

OPERATIONAL = 'operational'
CONFIG = 'config'
SETTINGS = 'settings'

PERMISSIONS = ['view', 'create', 'own', 'update', 'delete']
PERMISSION_LABELS = {
    'view': 'View Only',
    'create': 'Create',
    'own': 'Create and Edit Own Only',
    'update': 'Update',
    'delete': 'Delete',
}
# perm_read, perm_write, perm_create, perm_unlink
PERMISSION_ACCESS = {
    'view': '1,0,0,0',
    'create': '1,0,1,0',
    'own': '1,1,1,0',
    'update': '1,1,0,0',
    'delete': '1,0,0,1',
}

FULL = ('view', 'create', 'update', 'delete')
VIEW = ('view',)
OWN = ('view', 'own')

ROLE_ORDER = ['Administrator', 'Manager', 'Employee', 'View Only']


def default_roles(app_name, models):
    operational = [model[0] for model in models if model[2] == OPERATIONAL]
    return {
        'Administrator': (
            'Full access to every %s record, including Configuration and Settings.' % app_name,
            {model[0]: FULL for model in models},
        ),
        'Manager': (
            'Creates, updates and deletes every %s record. No access to Configuration or '
            'Settings.' % app_name,
            {key: FULL for key in operational},
        ),
        'Employee': (
            'Creates and edits the %s records they created or are named on. No access to '
            'Configuration or Settings.' % app_name,
            {key: OWN for key in operational},
        ),
        'View Only': (
            'Views %s records without changing them. No access to Configuration or '
            'Settings.' % app_name,
            {key: VIEW for key in operational},
        ),
    }


def module_roles(spec):
    roles = getattr(spec, 'ROLES', None) or default_roles(spec.APP_NAME, spec.MODELS)
    order = ROLE_ORDER + [name for name in roles if name not in ROLE_ORDER]
    return [(name, roles[name]) for name in order if name in roles]


def role_access(spec, access):
    """[(key, permission)] for a role's ``{key: permissions}``, in model order."""
    return [
        (model[0], permission)
        for model in spec.MODELS
        for permission in PERMISSIONS
        if permission in access.get(model[0], ())
    ]


def group_xmlid(module, spec, key, permission):
    return '%s.group_%s_%s_%s' % (module, spec.PREFIX, key, permission)


def role_group_xmlids(module, spec, role_name, access):
    """Every group XML ID a role is made of: its model groups plus ROLE_EXTRA_GROUPS."""
    return [
        group_xmlid(module, spec, key, permission)
        for key, permission in role_access(spec, access)
    ] + list(getattr(spec, 'ROLE_EXTRA_GROUPS', {}).get(role_name, []))


def role_names(spec):
    """Full names ("<APP_NAME> – <role>") of a module's roles."""
    return ['%s – %s' % (spec.APP_NAME, name) for name, _role in module_roles(spec)]


def pre_migrate_old_groups(cr, spec, old_group_xmlids, release_xmlids=()):
    """pre-migrate helper for modules moving to access levels (plain SQL, so it works
    whatever has been loaded yet).

    Removes Permission Management role lines that use the old groups. Roles left empty
    are deleted, except those named like one of the module's new roles: they are kept
    (with their profiles) and refilled with the new groups when the roles are loaded.

    ``release_xmlids`` are records the module still defines that were loaded as noupdate
    data (e.g. a feature group moving to a new privilege): Odoo ignores later changes to
    such records, so they are switched to updatable first.
    """
    if release_xmlids:
        cr.execute("""
            UPDATE ir_model_data SET noupdate = false
             WHERE module || '.' || name = ANY(%s)
        """, [list(release_xmlids)])
    cr.execute("SELECT to_regclass('permission_role_line')")
    if not cr.fetchone()[0]:
        return
    cr.execute("""
        SELECT d.res_id FROM ir_model_data d
         WHERE d.model = 'res.groups' AND d.module || '.' || d.name = ANY(%s)
    """, [list(old_group_xmlids)])
    group_ids = [row[0] for row in cr.fetchall()]
    if not group_ids:
        return
    cr.execute(
        "DELETE FROM permission_role_line WHERE group_id = ANY(%s) RETURNING role_id", [group_ids])
    role_ids = list({row[0] for row in cr.fetchall()})
    if role_ids:
        cr.execute("""
            DELETE FROM permission_role r
             WHERE r.id = ANY(%s)
               AND NOT EXISTS (SELECT 1 FROM permission_role_line l WHERE l.role_id = r.id)
               AND NOT (r.name = ANY(%s))
        """, [role_ids, role_names(spec)])


def migrate_old_groups(env, module, spec, old_group_roles, remove_from_roles=True):
    """post-migrate helper for modules moving to access levels.

    ``old_group_roles`` is ``[(old group XML ID, role name)]``: users in each old group get
    that role's groups. Unless ``remove_from_roles`` is False (for groups that stay, such
    as another app's), the old groups are then deleted - Odoo keeps records loaded as
    noupdate data, so they would otherwise linger - along with their privileges once
    those have no groups left (pair with pre_migrate_old_groups for role lines).
    """
    roles = dict(module_roles(spec))
    old_groups = env['res.groups']
    # Each user gets the role of the last (highest) old group they had, directly or
    # implied, so a Manager doesn't also collect the Employee groups their old group implied.
    user_roles = {}
    for old_xmlid, role_name in old_group_roles:
        old_group = env.ref(old_xmlid, raise_if_not_found=False)
        if not old_group:
            continue
        old_groups |= old_group
        for user in old_group.all_user_ids:
            user_roles[user] = role_name
    # The database administrator keeps full access (on a fresh install the generated
    # security file grants it; on an upgrade Odoo skips that noupdate record).
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin and 'Administrator' in roles:
        user_roles[admin] = 'Administrator'
    for role_name in set(user_roles.values()):
        users = env['res.users'].union(*[user for user, name in user_roles.items() if name == role_name])
        group_ids = [
            env.ref(xmlid).id
            for xmlid in role_group_xmlids(module, spec, role_name, roles[role_name][1])
        ]
        users.write({'group_ids': [(4, group_id) for group_id in group_ids]})
    if not remove_from_roles or not old_groups:
        return
    old_privileges = old_groups.privilege_id
    # Role lines whose group moved to another privilege (a feature group kept by the
    # module). Plain SQL: Permission Management may not be loaded yet in this upgrade.
    env.cr.execute("SELECT to_regclass('permission_role_line')")
    has_role_lines = bool(env.cr.fetchone()[0])
    if has_role_lines:
        env.cr.execute("""
            UPDATE permission_role_line l SET privilege_id = g.privilege_id
              FROM res_groups g
             WHERE g.id = l.group_id AND g.privilege_id IS NOT NULL
               AND l.privilege_id IS DISTINCT FROM g.privilege_id
        """)
    # Their old access rows are only removed when the upgrade ends; they block the delete.
    env['ir.model.access'].search([('group_id', 'in', old_groups.ids)]).unlink()
    old_groups.unlink()
    for privilege in old_privileges.exists().filtered(lambda privilege: not privilege.group_ids):
        if has_role_lines:
            env.cr.execute("SELECT 1 FROM permission_role_line WHERE privilege_id = %s LIMIT 1", [privilege.id])
            if env.cr.fetchone():
                continue  # still used by a role; harmless to keep
        privilege.unlink()
