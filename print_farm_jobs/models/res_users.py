from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    print_farm_role = fields.Selection(
        [
            ('user', 'User'),
            ('manager', 'Manager'),
            ('administrator', 'Administrator'),
        ],
        string='Print Farm',
        compute='_compute_print_farm_role',
        inverse='_inverse_print_farm_role',
    )

    @api.depends('group_ids')
    def _compute_print_farm_role(self):
        admin_group = self.env.ref('print_farm_jobs.group_print_farm_administrator')
        manager_group = self.env.ref('print_farm_jobs.group_print_farm_manager')
        user_group = self.env.ref('print_farm_jobs.group_print_farm_user')
        for user in self:
            # Use all_group_ids so that groups implied via implied_ids are included
            effective = user.all_group_ids
            if admin_group in effective:
                user.print_farm_role = 'administrator'
            elif manager_group in effective:
                user.print_farm_role = 'manager'
            elif user_group in effective:
                user.print_farm_role = 'user'
            else:
                user.print_farm_role = False

    def _inverse_print_farm_role(self):
        admin_group = self.env.ref('print_farm_jobs.group_print_farm_administrator')
        manager_group = self.env.ref('print_farm_jobs.group_print_farm_manager')
        user_group = self.env.ref('print_farm_jobs.group_print_farm_user')
        all_pf_group_ids = (admin_group | manager_group | user_group).ids
        for user in self:
            # Remove all Print Farm groups, then add only the selected level.
            # Odoo's implied_ids mechanism will automatically cascade upward:
            #   administrator → manager → user (via all_group_ids)
            remove_cmds = [(3, gid) for gid in all_pf_group_ids]
            if user.print_farm_role == 'administrator':
                add_cmds = [(4, admin_group.id)]
            elif user.print_farm_role == 'manager':
                add_cmds = [(4, manager_group.id)]
            elif user.print_farm_role == 'user':
                add_cmds = [(4, user_group.id)]
            else:
                add_cmds = []
            user.write({'group_ids': remove_cmds + add_cmds})
