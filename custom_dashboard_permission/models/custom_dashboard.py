from odoo import fields, models


class CustomDashboard(models.Model):
    _inherit = 'custom.dashboard'

    permission_profile_ids = fields.Many2many(
        'permission.profile', 'custom_dashboard_permission_profile_rel', 'dashboard_id', 'profile_id',
        string='Shared with Profiles',
        help='Users on these Permission Profiles can open the dashboard.',
    )

    def write(self, vals):
        old_profiles = self.permission_profile_ids if 'permission_profile_ids' in vals else None
        result = super().write(vals)
        if old_profiles is not None:
            (old_profiles | self.permission_profile_ids).user_ids._sync_profile_groups()
        return result
