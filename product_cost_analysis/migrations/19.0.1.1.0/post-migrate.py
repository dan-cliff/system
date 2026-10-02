"""Access moves from other apps' groups to per-model access levels (View Only,
Create, Create and Edit Own Only, Update and Delete for each model). Give users of each
of those groups the groups of the matching new role, so nobody loses access."""
from odoo import SUPERUSER_ID, api

from odoo.addons.permission_management.access_levels_lib import migrate_old_groups
from odoo.addons.product_cost_analysis import access_levels

OLD_GROUP_ROLES = [
    ('base.group_user', 'Manager'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # These groups belong to other apps and stay, so leave them in Permission Management roles.
    migrate_old_groups(env, 'product_cost_analysis', access_levels, OLD_GROUP_ROLES, remove_from_roles=False)
