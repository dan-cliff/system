# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.checklists.models.checklist_group_access import PERMISSIONS

ROLE_NAME_PREFIX = 'Checklists – '


class ChecklistGroupAccess(models.Model):
    _inherit = 'checklist.group.access'

    role_id = fields.Many2one('permission.role', string='Role', ondelete='set null')

    @api.model
    def _sync_for_groups(self, checklist_groups):
        result = super()._sync_for_groups(checklist_groups)
        Role = self.env['permission.role'].sudo()
        for access in checklist_groups.with_context(active_test=False).sudo().access_ids:
            name = ROLE_NAME_PREFIX + access._name_for(access.checklist_group_id.name)
            if access.role_id:
                if access.role_id.name != name:
                    access.role_id.name = name
                continue
            access.role_id = Role.create({
                'name': name,
                'description': PERMISSIONS[access.code][1],
                'line_ids': [(0, 0, {
                    'privilege_id': access.privilege_id.id,
                    'group_id': access.res_group_id.id,
                })],
            })
        return result

    def _remove(self):
        # Removing a Role takes its group away from the profiles' users.
        roles = self.sudo().role_id
        users = roles.profile_ids.user_ids
        roles.unlink()
        result = super()._remove()
        if users:
            users._sync_profile_groups()
        return result
