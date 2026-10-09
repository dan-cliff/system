from odoo import models

DASHBOARD_USER_GROUP = 'custom_dashboard.group_dashboard_user'


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _sync_profile_groups(self):
        """Also give Dashboards "User" access to users whose profile lists
        dashboards, managed like the profile's role groups so it is removed
        again when the profile stops granting it."""
        super()._sync_profile_groups()
        group = self.env.ref(DASHBOARD_USER_GROUP, raise_if_not_found=False)
        if not group:
            return
        for user in self:
            needs = bool(user.permission_profile_id.sudo().dashboard_ids)
            managed = group in user.profile_managed_group_ids
            if needs and not managed and group not in user.sudo().all_group_ids:
                user.sudo().write({
                    'group_ids': [(4, group.id)],
                    'profile_managed_group_ids': [(4, group.id)],
                })
            elif not needs and managed and group not in user.permission_profile_id.role_ids.group_ids:
                user.sudo().write({
                    'group_ids': [(3, group.id)],
                    'profile_managed_group_ids': [(3, group.id)],
                })
