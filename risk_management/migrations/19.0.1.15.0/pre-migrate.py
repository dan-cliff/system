"""Before the new access levels load, remove the old groups from Permission Management
roles: roles left empty are deleted, except those named like one of this app's new roles,
which are refilled with the new groups (keeping their profiles)."""
from odoo.addons.permission_management.access_levels_lib import pre_migrate_old_groups
from odoo.addons.risk_management import access_levels

OLD_GROUPS = [
    'risk_management.group_risk_administrator',
    'risk_management.group_risk_leader_adults',
    'risk_management.group_risk_leader_youth',
    'risk_management.group_risk_read_only',
]


def migrate(cr, version):
    pre_migrate_old_groups(cr, access_levels, OLD_GROUPS)
