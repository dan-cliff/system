from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    permission_profile_id = fields.Many2one(
        comodel_name='permission.profile',
        string='Permission Profile',
        ondelete='set null',
    )
    permission_profile_override = fields.Boolean(
        string='Profile Manually Overridden',
        default=False,
        help='When enabled, changing the user\'s job position will not automatically update their profile.',
    )
    profile_managed_group_ids = fields.Many2many(
        comodel_name='res.groups',
        relation='permission_mgmt_user_groups_rel',
        column1='user_id',
        column2='group_id',
        string='Profile Managed Groups',
    )
    effective_group_ids = fields.Many2many(
        comodel_name='res.groups',
        string='Effective Groups (Profile)',
        compute='_compute_effective_group_ids',
    )
    job_default_profile_id = fields.Many2one(
        comodel_name='permission.profile',
        string='Job Position Default Profile',
        compute='_compute_job_default_profile_id',
    )

    @api.depends('permission_profile_id', 'permission_profile_id.role_ids', 'permission_profile_id.role_ids.group_ids')
    def _compute_effective_group_ids(self):
        for user in self:
            if user.permission_profile_id:
                user.effective_group_ids = user.permission_profile_id.role_ids.group_ids
            else:
                user.effective_group_ids = self.env['res.groups']

    @api.depends('employee_id', 'employee_id.job_id', 'employee_id.job_id.default_permission_profile_id')
    def _compute_job_default_profile_id(self):
        for user in self:
            employee = user.employee_id
            if employee and employee.job_id and employee.job_id.default_permission_profile_id:
                user.job_default_profile_id = employee.job_id.default_permission_profile_id
            else:
                user.job_default_profile_id = False

    def _sync_profile_groups(self):
        """Sync group memberships based on the user's current permission profile."""
        for user in self:
            profile = user.permission_profile_id
            new_groups = profile.role_ids.group_ids if profile else self.env['res.groups']
            old_managed = user.profile_managed_group_ids

            groups_to_remove = old_managed - new_groups
            groups_to_add = new_groups - user.sudo().group_ids

            if groups_to_remove or groups_to_add or old_managed != new_groups:
                user.sudo().write({
                    'group_ids': (
                        [(3, g.id) for g in groups_to_remove] +
                        [(4, g.id) for g in groups_to_add]
                    ),
                    'profile_managed_group_ids': [(6, 0, new_groups.ids)],
                })

    def write(self, vals):
        if 'permission_profile_id' in vals and not self.env.context.get('auto_profile_sync'):
            if 'permission_profile_override' not in vals:
                vals = dict(vals, permission_profile_override=True)
        result = super().write(vals)
        if 'permission_profile_id' in vals:
            self._sync_profile_groups()
        return result

    def action_reset_profile_to_default(self):
        """Reset the user's profile to the job position default."""
        for user in self:
            employee = user.employee_id
            if employee and employee.job_id and employee.job_id.default_permission_profile_id:
                user.with_context(auto_profile_sync=True).write({
                    'permission_profile_id': employee.job_id.default_permission_profile_id.id,
                    'permission_profile_override': False,
                })
