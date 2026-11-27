from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestListColumnRoles(TransactionCase):

    def test_roles_per_app(self):
        App = self.env['list.column.app']
        App._sync_apps()
        apps = App.search([])
        self.assertTrue(apps)
        for app in apps:
            self.assertTrue(app.roles_done)
            self.assertEqual(app.role_id.name, f'{app.name} – List Column Customiser')
            self.assertEqual(app.role_id.line_ids.group_id, app.group_id)
        self.assertTrue(self.env.ref('list_column_config_permission.role_list_column_admin'))

    def test_new_app_adds_privilege_to_admin_role(self):
        App = self.env['list.column.app']
        App._sync_apps()  # apps of modules installed since the last sync
        category = self.env['ir.module.category'].create({'name': 'Test App'})
        privilege = self.env['res.groups.privilege'].create({'name': 'Test App', 'category_id': category.id})
        admin_group = self.env['res.groups'].create({'name': 'Administrator', 'privilege_id': privilege.id})
        admin_role = self.env['permission.role'].create({
            'name': 'Test App – Administrator',
            'line_ids': [(0, 0, {'privilege_id': privilege.id, 'group_id': admin_group.id})],
        })
        menu = self.env['ir.ui.menu'].create({'name': 'Test App'})
        self.patch(type(App), '_app_category', lambda self, menu: category)
        App._sync_apps()
        app = App.search([('menu_id', '=', menu.id)])
        self.assertIn(app.group_id, admin_role.line_ids.group_id)

        # removing the app removes its role and its line on the admin role
        role = app.role_id
        menu.unlink()
        App._sync_apps()
        self.assertFalse(role.exists())
        self.assertEqual(admin_role.line_ids.group_id, admin_group)
