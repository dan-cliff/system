"""The Scouting based access levels (Read Only, Leader of Youth, Leader of Adults,
Administrator) are replaced by per-model access level groups. Give each user who had one
of the old levels the groups of the matching new role, and remove the old levels from
Permission Management roles (deleting roles, such as Leader of Youth, left empty) so the
old groups can be removed once the upgrade finishes."""
from odoo import SUPERUSER_ID, api

from odoo.addons.permission_management.access_levels_lib import migrate_old_groups
from odoo.addons.risk_management import access_levels

OLD_GROUP_ROLES = [
    ('risk_management.group_risk_read_only', 'View Only'),
    ('risk_management.group_risk_leader_youth', 'Employee'),
    ('risk_management.group_risk_leader_adults', 'Manager'),
    ('risk_management.group_risk_administrator', 'Administrator'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_old_groups(env, 'risk_management', access_levels, OLD_GROUP_ROLES)
