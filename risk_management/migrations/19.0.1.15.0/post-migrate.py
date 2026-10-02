"""The Scouting based access levels (Read Only, Leader of Youth, Leader of Adults,
Administrator) are replaced by per-model View Only / Create / Update / Delete groups.
Give each user who had one of the old levels the groups of the matching new role; the
old groups are removed once the upgrade finishes."""
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
    for old_xmlid, role_name in OLD_GROUP_ROLES:
        old_group = env.ref(old_xmlid, raise_if_not_found=False)
        if not old_group or not old_group.all_user_ids:
            continue
        new_groups = env['res.groups'].browse([
            env.ref(group_xmlid(key, permission)).id
            for key, permission in role_access(role_name)
        ])
        old_group.all_user_ids.write({'group_ids': [(4, group.id) for group in new_groups]})
