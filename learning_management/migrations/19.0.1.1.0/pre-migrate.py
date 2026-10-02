"""Before the new access levels load, remove the old groups from Permission Management
roles: roles left empty are deleted, except those named like one of this app's new roles,
which are refilled with the new groups (keeping their profiles)."""
from odoo.addons.permission_management.access_levels_lib import pre_migrate_old_groups
from odoo.addons.learning_management import access_levels

OLD_GROUPS = [
    'learning_management.group_lms_admin',
    'learning_management.group_lms_employee',
    'learning_management.group_lms_facilitator',
    'learning_management.group_lms_manager',
    'learning_management.group_lms_people_leader',
]


def migrate(cr, version):
    pre_migrate_old_groups(cr, access_levels, OLD_GROUPS)
