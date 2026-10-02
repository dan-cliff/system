"""Risk Templates and the Configuration lists are now Administrator (and Risk Manager)
only, and every model gained a Create and Edit Own Only group. Bring the Risk Management
roles created by 19.0.1.15.0 in line with access_levels.py; users on those roles through
a Permission Management profile are re-synced by the role write."""
from odoo import SUPERUSER_ID, api

from odoo.addons.permission_management import access_levels_lib
from odoo.addons.risk_management import access_levels


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'permission.role' not in env:
        return
    for role_name, (description, access) in access_levels_lib.module_roles(access_levels):
        role = env['permission.role'].search(
            [('name', '=', '%s – %s' % (access_levels.APP_NAME, role_name))], limit=1)
        if not role:
            continue
        groups = [
            env.ref(xmlid)
            for xmlid in access_levels_lib.role_group_xmlids('risk_management', access_levels, role_name, access)
        ]
        role.write({
            'description': description,
            'line_ids': [(5, 0, 0)] + [
                (0, 0, {'privilege_id': group.privilege_id.id, 'group_id': group.id})
                for group in groups if group.privilege_id
            ],
        })
