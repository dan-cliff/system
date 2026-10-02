"""Before the new access levels load, remove the old groups from Permission Management
roles: roles left empty are deleted, except those named like one of this app's new roles,
which are refilled with the new groups (keeping their profiles)."""
from odoo.addons.permission_management.access_levels_lib import pre_migrate_old_groups
from odoo.addons.dangerous_goods import access_levels

OLD_GROUPS = [
    'dangerous_goods.group_dg_admin',
    'dangerous_goods.group_dg_manager',
    'dangerous_goods.group_dg_user',
]


def migrate(cr, version):
    pre_migrate_old_groups(cr, access_levels, OLD_GROUPS)
