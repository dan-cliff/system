"""Before the new access levels load, remove the old groups from Permission Management
roles: roles left empty are deleted, except those named like one of this app's new roles,
which are refilled with the new groups (keeping their profiles)."""
from odoo.addons.permission_management.access_levels_lib import pre_migrate_old_groups
from odoo.addons.membership_management import access_levels

OLD_GROUPS = [
    'membership_management.group_membership_administrator',
    'membership_management.group_membership_employee',
    'membership_management.group_membership_manager',
    'membership_management.group_membership_memberships_manager',
]


def migrate(cr, version):
    pre_migrate_old_groups(cr, access_levels, OLD_GROUPS)
