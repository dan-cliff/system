"""Access moves from the old app-wide groups to per-model access levels (View Only,
Create, Create and Edit Own Only, Update and Delete for each model). Give users of each
old group the groups of the matching new role, then delete the old groups (pre-migrate
already took them out of Permission Management roles)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.permission_management.access_levels_lib import migrate_old_groups
from odoo.addons.video_production import access_levels

OLD_GROUP_ROLES = [
    ('video_production.group_video_production_user', 'Employee'),
    ('video_production.group_video_production_manager', 'Administrator'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_old_groups(env, 'video_production', access_levels, OLD_GROUP_ROLES)
