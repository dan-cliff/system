from odoo import api, fields, models
from odoo.addons.permission_management.hooks import post_init_hook


class PermissionRole(models.Model):
    _name = 'permission.role'
    _description = 'Permission Role'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    line_ids = fields.One2many(
        comodel_name='permission.role.line',
        inverse_name='role_id',
        string='Privileges',
    )
    group_ids = fields.Many2many(
        comodel_name='res.groups',
        string='Security Groups',
        compute='_compute_group_ids',
    )
    profile_ids = fields.Many2many(
        comodel_name='permission.profile',
        relation='permission_profile_role_rel',
        column1='role_id',
        column2='profile_id',
        string='Profiles',
    )

    @api.depends('line_ids.group_id')
    def _compute_group_ids(self):
        for role in self:
            role.group_ids = role.line_ids.mapped('group_id')

    @api.model
    def _load_role_library(self):
        """Safe entry point called by permission_role_data.xml.
        Delegates to the post_init_hook which skips any missing modules."""
        post_init_hook(self.env)

    def write(self, vals):
        result = super().write(vals)
        if 'line_ids' in vals:
            users = self.env['res.users']
            for role in self:
                for profile in role.profile_ids:
                    users |= profile.user_ids
            if users:
                users._sync_profile_groups()
        return result
