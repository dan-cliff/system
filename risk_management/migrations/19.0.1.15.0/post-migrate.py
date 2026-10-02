"""The Scouting based access levels (Read Only, Leader of Youth, Leader of Adults,
Administrator) are replaced by per-model View Only / Create / Update / Delete groups.
Give each user who had one of the old levels the groups of the matching new role, and
remove the old levels from Permission Management roles (deleting roles, such as Leader of
Youth, left with nothing in them) so the old groups can be removed once the upgrade
finishes."""
from odoo import SUPERUSER_ID, api

from odoo.addons.risk_management.access_levels import group_xmlid, role_access

OLD_GROUP_ROLES = [
    ('risk_management.group_risk_read_only', 'View Only'),
    ('risk_management.group_risk_leader_youth', 'Employee'),
    ('risk_management.group_risk_leader_adults', 'Manager'),
    ('risk_management.group_risk_administrator', 'Administrator'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    old_groups = env['res.groups']
    for old_xmlid, role_name in OLD_GROUP_ROLES:
        old_group = env.ref(old_xmlid, raise_if_not_found=False)
        if not old_group:
            continue
        old_groups |= old_group
        if not old_group.all_user_ids:
            continue
        new_groups = env['res.groups'].browse([
            env.ref(group_xmlid(key, permission)).id
            for key, permission in role_access(role_name)
        ])
        old_group.all_user_ids.write({'group_ids': [(4, group.id) for group in new_groups]})

    if old_groups and 'permission.role.line' in env:
        old_lines = env['permission.role.line'].search([('group_id', 'in', old_groups.ids)])
        roles = old_lines.role_id
        old_lines.unlink()
        roles.filtered(lambda role: not role.line_ids).unlink()
