"""Access moves from the old app-wide groups to per-model access levels (View Only,
Create, Create and Edit Own Only, Update and Delete for each model). Give users of each
old group the groups of the matching new role, then delete the old groups (pre-migrate
already took them out of Permission Management roles)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.permission_management.access_levels_lib import migrate_old_groups
from odoo.addons.report_builder import access_levels
from odoo.addons.report_builder.hooks import _setup_admin_profile

OLD_GROUP_ROLES = [
    ('report_builder.group_report_builder_user', 'Employee'),
    ('report_builder.group_report_builder_manager', 'Administrator'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_old_groups(env, 'report_builder', access_levels, OLD_GROUP_ROLES)
    # The old Manager role was just removed; put the new Administrator role in the
    # System Administrator profile instead.
    _setup_admin_profile(env)
