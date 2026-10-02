from odoo import api, models

from odoo.addons.risk_management.access_levels import (
    ROLE_NAME_PREFIX,
    ROLES,
    group_xmlid,
    role_access,
)


class RiskPermissionRoles(models.AbstractModel):
    _name = 'risk.permission.roles'
    _description = 'Risk Management Permission Roles'

    @api.model
    def _sync_permission_roles(self):
        """Create the Risk Management roles in Permission Management, if that app is installed.

        Runs on every install/upgrade of risk_management (and when permission_management is
        installed). Roles that already exist are left alone so any changes made to them in
        Permission Management are kept.
        """
        if 'permission.role' not in self.env:
            return
        Role = self.env['permission.role'].sudo()
        for role_name, (description, _access) in ROLES.items():
            name = ROLE_NAME_PREFIX + role_name
            if Role.search_count([('name', '=', name)], limit=1):
                continue
            lines = []
            for key, permission in role_access(role_name):
                group = self.env.ref(group_xmlid(key, permission))
                lines.append((0, 0, {
                    'privilege_id': group.privilege_id.id,
                    'group_id': group.id,
                }))
            Role.create({'name': name, 'description': description, 'line_ids': lines})
