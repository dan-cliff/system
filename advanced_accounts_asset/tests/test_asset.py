from odoo.tests import Form, tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestAssetAccounts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['advanced.account'].create({'name': 'Tools R Us'})
        cls.maker = cls.env['advanced.account'].create({'name': 'Makita'})
        cls.owner = cls.env['advanced.contact'].create({'name': 'Olive Owner'})
        cls.asset_type = cls.env['asset.type'].create({'name': 'Power Tools'})

    def test_remap_fields_follow_and_set_partners(self):
        asset = self.env['asset.asset'].create({
            'name': 'Drill',
            'asset_type_id': self.asset_type.id,
            'adv_supplier_id': self.supplier.id,
            'adv_manufacturer_id': self.maker.id,
            'adv_owner_id': self.owner.id,
        })
        self.assertEqual(asset.supplier_id, self.supplier.partner_id)
        self.assertEqual(asset.manufacturer_id, self.maker.partner_id)
        self.assertEqual(asset.owner_id, self.owner.partner_id)
        asset.supplier_id = self.maker.partner_id
        self.assertEqual(asset.adv_supplier_id, self.maker)

    def test_form_onchange(self):
        form = Form(self.env['asset.asset'])
        form.name = 'Ladder'
        form.asset_type_id = self.asset_type
        form.adv_supplier_id = self.supplier
        self.assertEqual(form.supplier_id, self.supplier.partner_id)
