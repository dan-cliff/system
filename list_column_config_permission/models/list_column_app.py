from odoo import api, fields, models


class ListColumnApp(models.Model):
    _inherit = 'list.column.app'

    role_id = fields.Many2one(
        comodel_name='permission.role',
        string='Customiser Role',
        ondelete='set null',
        readonly=True,
    )
    roles_done = fields.Boolean(
        readonly=True,
        help='The app has had its role made and its privilege added to its Administrator roles. '
             'Done once, so roles changed or deleted by an administrator stay that way.',
    )

    @api.model
    def _sync_apps(self):
        res = super()._sync_apps()
        self._sync_permission_roles()
        return res

    @api.model
    def _sync_permission_roles(self):
        apps = self.sudo().with_context(active_test=False).search([
            ('roles_done', '=', False), ('group_id', '!=', False),
        ])
        Role = self.env['permission.role'].sudo()
        own_category = self.env.ref('list_column_config.module_category_list_column_config')
        for app in apps:
            line = {'privilege_id': app.privilege_id.id, 'group_id': app.group_id.id}
            role = Role.create({
                'name': self.env._('%s – List Column Customiser', app.name),
                'description': self.env._(
                    'Customise the columns of the list views in %s, for all users.', app.name),
                'line_ids': [(0, 0, line)],
            })
            category = app.privilege_id.category_id
            if category and category != own_category:
                admin_roles = self.env['permission.role.line'].sudo().with_context(lang='en_US').search([
                    ('privilege_id.category_id', '=', category.id),
                    ('group_id.name', '=', 'Administrator'),
                ]).role_id - role
                for admin_role in admin_roles.filtered(lambda r: app.group_id not in r.line_ids.group_id):
                    # write() keeps the role's users' groups in step
                    admin_role.write({'line_ids': [(0, 0, line)]})
            app.write({'role_id': role.id, 'roles_done': True})
        return True

    def _remove(self):
        groups = self.sudo().group_id
        lines = self.env['permission.role.line'].sudo().search([('group_id', 'in', groups.ids)])
        roles = self.sudo().role_id
        by_role = {}
        for line in lines:
            by_role.setdefault(line.role_id, []).append(line.id)
        for role, line_ids in by_role.items():
            # write() keeps the role's users' groups in step
            role.write({'line_ids': [(2, line_id) for line_id in line_ids]})
        roles.exists().filtered(lambda role: not role.line_ids).unlink()
        return super()._remove()
