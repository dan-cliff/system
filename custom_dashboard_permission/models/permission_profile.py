from odoo import fields, models


class PermissionProfile(models.Model):
    _inherit = 'permission.profile'

    dashboard_ids = fields.Many2many(
        'custom.dashboard', 'custom_dashboard_permission_profile_rel', 'profile_id', 'dashboard_id',
        string='Dashboards',
        help='Dashboards that users on this profile can open. They are given Dashboards "User" '
             'access automatically.',
    )

    def write(self, vals):
        result = super().write(vals)
        if 'dashboard_ids' in vals and 'role_ids' not in vals:
            # Changing the roles already re-syncs the users' groups.
            self.user_ids._sync_profile_groups()
        return result
