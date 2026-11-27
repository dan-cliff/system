"""Add the Sprint and Epic permissions to the standard roles of an existing database.

The roles are noupdate data (admins may have adjusted them), so the lines added to
data/permission_role_data.xml for sprints and epics don't reach roles that already
exist. Add them here, leaving any line the role already has.
"""
from odoo import SUPERUSER_ID, api

# role xml id -> [(privilege xml id, group xml id)] added in this version.
NEW_LINES = {
    'role_dev_admin': [('privilege_dev_%s_%s' % (m, p), 'group_dev_%s_%s' % (m, p))
                       for m in ('sprint', 'epic')
                       for p in ('create_only', 'edit_own', 'edit_team', 'edit_all', 'view_all',
                                 'delete_own', 'delete_all')],
    'role_dev_manager': [('privilege_dev_%s_%s' % (m, p), 'group_dev_%s_%s' % (m, p))
                         for m in ('sprint', 'epic') for p in ('edit_team', 'view_all')],
    'role_dev_employee': [('privilege_dev_%s_%s' % (m, p), 'group_dev_%s_%s' % (m, p))
                          for m in ('sprint', 'epic') for p in ('edit_own', 'view_all')],
    'role_dev_developer': [('privilege_dev_%s_view_all' % m, 'group_dev_%s_view_all' % m) for m in ('sprint', 'epic')],
    'role_dev_designer': [('privilege_dev_epic_edit_all', 'group_dev_epic_edit_all'),
                          ('privilege_dev_sprint_view_all', 'group_dev_sprint_view_all')],
    'role_dev_release_manager': [('privilege_dev_%s_view_all' % m, 'group_dev_%s_view_all' % m)
                                 for m in ('sprint', 'epic')],
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for role_xmlid, lines in NEW_LINES.items():
        role = env.ref('dev_management_permission.%s' % role_xmlid, raise_if_not_found=False)
        if not role:
            continue
        have = set(role.line_ids.mapped('group_id').ids)
        commands = []
        for privilege_xmlid, group_xmlid in lines:
            privilege = env.ref('dev_management.%s' % privilege_xmlid, raise_if_not_found=False)
            group = env.ref('dev_management.%s' % group_xmlid, raise_if_not_found=False)
            if privilege and group and group.id not in have:
                commands.append((0, 0, {'privilege_id': privilege.id, 'group_id': group.id}))
        if commands:
            role.write({'line_ids': commands})
