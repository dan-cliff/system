from odoo import api, fields, models


class AssetAsset(models.Model):
    _name = 'asset.asset'
    _inherit = ['asset.asset', 'advanced.accounts.remap.mixin']
    # Assigned To was an employee: the Contact is a field of its own, and the
    # employee field is kept (and shown while the Contact is empty).
    _adv_remap = {
        'adv_supplier_id': 'supplier_id',
        'adv_manufacturer_id': 'manufacturer_id',
        'adv_sw_supplier_id': 'sw_supplier_id',
        'adv_owner_id': 'owner_id',
        'adv_assigned_to_id': False,
    }

    # The partner fields they stand in for (kept, and filled from them).
    supplier_id = fields.Many2one(string='Supplier (Partner)')
    manufacturer_id = fields.Many2one(string='Manufacturer (Partner)')
    sw_supplier_id = fields.Many2one(string='Software Supplier (Partner)')
    owner_id = fields.Many2one(string='Owner (Partner)')
    assigned_to_id = fields.Many2one(string='Assigned To (Employee)')

    adv_supplier_id = fields.Many2one(
        'advanced.account', string='Supplier', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True)
    adv_manufacturer_id = fields.Many2one(
        'advanced.account', string='Manufacturer', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True)
    adv_sw_supplier_id = fields.Many2one(
        'advanced.account', string='Software Supplier', ondelete='set null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True)
    adv_owner_id = fields.Many2one(
        'advanced.contact', string='Owner', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The person who owns this asset.')
    adv_assigned_to_id = fields.Many2one(
        'advanced.contact', string='Assigned To', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The person currently responsible for this asset.')

    @api.onchange('adv_supplier_id')
    def _onchange_adv_supplier_id(self):
        self._adv_remap_push('adv_supplier_id')

    @api.onchange('adv_manufacturer_id')
    def _onchange_adv_manufacturer_id(self):
        self._adv_remap_push('adv_manufacturer_id')

    @api.onchange('adv_sw_supplier_id')
    def _onchange_adv_sw_supplier_id(self):
        self._adv_remap_push('adv_sw_supplier_id')

    @api.onchange('adv_owner_id')
    def _onchange_adv_owner_id(self):
        self._adv_remap_push('adv_owner_id')


class AssetMaintenanceLog(models.Model):
    _name = 'asset.maintenance.log'
    _inherit = ['asset.maintenance.log', 'advanced.accounts.remap.mixin']
    _adv_remap = {'adv_supplier_id': 'supplier_id'}

    supplier_id = fields.Many2one(string='Supplier (Partner)')

    adv_supplier_id = fields.Many2one(
        'advanced.account', string='Supplier', ondelete='set null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True)

    @api.onchange('adv_supplier_id')
    def _onchange_adv_supplier_id(self):
        self._adv_remap_push('adv_supplier_id')
