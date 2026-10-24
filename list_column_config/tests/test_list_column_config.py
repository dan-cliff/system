from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestListColumnConfig(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.App = cls.env['list.column.app']
        cls.App._sync_apps()
        cls.contacts_menu = cls.env.ref('contacts.menu_contacts', raise_if_not_found=False)
        cls.settings_menu = cls.env.ref('base.menu_administration')
        cls.settings_app = cls.App.search([('menu_id', '=', cls.settings_menu.id)])
        cls.view = cls.env.ref('base.view_partner_tree')
        cls.user = new_test_user(cls.env, login='lcc_user', groups='base.group_user')
        cls.customiser = new_test_user(cls.env, login='lcc_customiser', groups='base.group_user')
        cls.customiser.group_ids = [(4, cls.settings_app.group_id.id)]

    def _columns(self, user=None):
        Partner = self.env['res.partner'].with_user(user or self.env.user)
        arch = etree.fromstring(Partner.get_view(self.view.id, 'list')['arch'])
        return {node.get('name'): node for node in arch if node.tag == 'field'}, arch

    def _open(self, user):
        action = self.env['list.column.wizard'].with_user(user).action_open_wizard(
            'res.partner', self.view.id, self.settings_menu.id)
        return self.env['list.column.wizard'].with_user(user).browse(action['res_id'])

    def test_sync_apps(self):
        roots = self.env['ir.ui.menu'].search([('parent_id', '=', False)])
        apps = self.App.search([('is_fallback', '=', False)])
        self.assertEqual(apps.menu_id, roots)
        self.assertTrue(self.App.search([('is_fallback', '=', True)]))
        app = self.settings_app
        self.assertEqual(app.privilege_id.name, 'Settings List Columns: Customise')
        self.assertEqual(app.group_id.name, 'Allowed')
        admin = self.env.ref('list_column_config.group_list_column_admin')
        self.assertIn(app.group_id, admin.implied_ids)
        # idempotent
        self.App._sync_apps()
        self.assertEqual(self.App.search_count([('menu_id', '=', app.menu_id.id)]), 1)

    def test_removed_app(self):
        menu = self.env['ir.ui.menu'].create({'name': 'Temporary App'})
        self.App._sync_apps()
        app = self.App.search([('menu_id', '=', menu.id)])
        group = app.group_id
        self.assertTrue(group)
        menu.unlink()
        self.App._sync_apps()
        self.assertFalse(app.exists())
        self.assertFalse(group.exists())

    def test_session_info(self):
        info = self.App.with_user(self.customiser)._session_info()
        self.assertFalse(info['all'])
        self.assertEqual(info['app_ids'], [self.settings_menu.id])
        info = self.App.with_user(self.user)._session_info()
        self.assertEqual(info['app_ids'], [])

    def test_access(self):
        with self.assertRaises(AccessError):
            self._open(self.user)
        wizard = self._open(self.customiser)
        self.assertTrue(wizard.line_ids)
        with self.assertRaises(AccessError):
            wizard.with_user(self.user).action_save()

    def test_save_layout_for_everyone(self):
        before, _arch = self._columns()
        self.assertIn('email', before)
        wizard = self._open(self.customiser)
        lines = {line.field_name: line for line in wizard.line_ids}
        # email first and renamed, phone hidden, ref added as optional
        lines['email'].write({'sequence': 0, 'label': 'E-mail Address'})
        lines['phone'].visibility = 'hidden'
        ref = wizard.field_option_ids.filtered(lambda o: o.name == 'ref')
        if 'ref' in lines:
            lines['ref'].visibility = 'optional_hide'
        else:
            wizard.line_ids = [(0, 0, {'field_option_id': ref.id, 'visibility': 'optional_hide', 'sequence': 999})]
        infos = wizard.action_save()['infos']
        self.assertTrue(infos['list_column_saved'])

        # every user gets the layout
        columns, arch = self._columns(self.user)
        fields = [node.get('name') for node in arch if node.tag == 'field' and node.get('column_invisible') not in ('1', 'True')]
        self.assertEqual(fields[0], 'email')
        self.assertEqual(columns['email'].get('string'), 'E-mail Address')
        self.assertIn(columns['phone'].get('column_invisible'), ('1', 'True'))
        self.assertEqual(columns['ref'].get('optional'), 'hide')

        # the wizard shows the saved layout
        wizard = self._open(self.customiser)
        first = wizard.line_ids.sorted('sequence')[0]
        self.assertEqual(first.field_name, 'email')
        self.assertEqual(first.label, 'E-mail Address')

        # reset
        wizard.action_reset()
        columns, _arch = self._columns(self.user)
        self.assertNotEqual(columns['email'].get('string'), 'E-mail Address')
        self.assertFalse(self.env['list.column.config'].search([('model', '=', 'res.partner')]))

    def test_unknown_field_is_skipped(self):
        config = self.env['list.column.config'].create({
            'model': 'res.partner',
            'view_id': self.view.id,
            'line_ids': [(0, 0, {'field_name': 'x_no_such_field', 'sequence': 1}),
                         (0, 0, {'field_name': 'email', 'sequence': 2, 'visibility': 'optional_hide'})],
        })
        columns, _arch = self._columns(self.user)
        self.assertEqual(columns['email'].get('optional'), 'hide')
        self.assertNotIn('x_no_such_field', columns)
        config.active = False
        columns, _arch = self._columns(self.user)
        self.assertNotEqual(columns['email'].get('optional'), 'hide')
