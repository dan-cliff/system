from odoo import api, fields, models


class PermissionProfile(models.Model):
    _name = 'permission.profile'
    _description = 'Permission Profile'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    role_ids = fields.Many2many(
        comodel_name='permission.role',
        relation='permission_profile_role_rel',
        column1='profile_id',
        column2='role_id',
        string='Roles',
    )
    effective_group_ids = fields.Many2many(
        comodel_name='res.groups',
        string='Effective Groups',
        compute='_compute_effective_group_ids',
    )
    user_ids = fields.One2many(
        comodel_name='res.users',
        inverse_name='permission_profile_id',
        string='Users',
    )
    user_count = fields.Integer(
        string='User Count',
        compute='_compute_user_count',
    )

    @api.depends('role_ids', 'role_ids.group_ids')
    def _compute_effective_group_ids(self):
        for profile in self:
            profile.effective_group_ids = profile.role_ids.group_ids

    @api.depends('user_ids')
    def _compute_user_count(self):
        for profile in self:
            profile.user_count = len(profile.user_ids)

    def write(self, vals):
        result = super().write(vals)
        if 'role_ids' in vals:
            users = self.mapped('user_ids')
            if users:
                users._sync_profile_groups()
        return result

    def action_view_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Users',
            'res_model': 'res.users',
            'view_mode': 'list,form',
            'domain': [('permission_profile_id', '=', self.id)],
            'context': {'default_permission_profile_id': self.id},
        }
