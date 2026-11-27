from odoo import api, fields, models


class PropertyProperty(models.Model):
    _name = 'property.property'
    _inherit = ['property.property', 'advanced.accounts.remap.mixin']
    _adv_remap = {
        'adv_landlord_id': 'landlord_id',
        'adv_agent_id': 'agent_id',
    }

    landlord_id = fields.Many2one(string='Landlord (Partner)')
    agent_id = fields.Many2one(string='Managing Agent (Partner)')

    adv_landlord_id = fields.Many2one(
        'advanced.account', string='Landlord', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The external owner of a property we lease.')
    adv_agent_id = fields.Many2one(
        'advanced.account', string='Managing Agent', ondelete='set null', tracking=True,
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The agent who manages the property on behalf of its owner.')

    @api.onchange('adv_landlord_id')
    def _onchange_adv_landlord_id(self):
        self._adv_remap_push('adv_landlord_id')

    @api.onchange('adv_agent_id')
    def _onchange_adv_agent_id(self):
        self._adv_remap_push('adv_agent_id')


class PropertyLease(models.Model):
    _name = 'property.lease'
    _inherit = ['property.lease', 'advanced.accounts.remap.mixin']
    _adv_remap = {
        'adv_party_id': 'partner_id',
        'adv_agent_id': 'agent_id',
    }

    partner_id = fields.Many2one(string='Landlord / Tenant (Partner)')
    agent_id = fields.Many2one(string='Agent (Partner)')

    adv_party_id = fields.Many2one(
        'advanced.account', string='Landlord / Tenant', ondelete='set null', tracking=True, index='btree_not_null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The other party to the lease: the landlord when we are the tenant, the tenant when we are '
             'the landlord.')
    adv_agent_id = fields.Many2one(
        'advanced.account', string='Agent', ondelete='set null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True)

    @api.onchange('adv_party_id')
    def _onchange_adv_party_id(self):
        self._adv_remap_push('adv_party_id')

    @api.onchange('adv_agent_id')
    def _onchange_adv_agent_id(self):
        self._adv_remap_push('adv_agent_id')


class PropertyContract(models.Model):
    _name = 'property.contract'
    _inherit = ['property.contract', 'advanced.accounts.mixin']
    _adv_partner_field = 'partner_id'

    partner_id = fields.Many2one(string='Supplier (Partner)')
