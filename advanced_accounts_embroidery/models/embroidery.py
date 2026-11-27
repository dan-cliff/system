from odoo import api, fields, models


class EmbroideryJob(models.Model):
    _name = 'embroidery.job'
    _inherit = ['embroidery.job', 'advanced.accounts.mixin']


class EmbroideryDesign(models.Model):
    _name = 'embroidery.design'
    _inherit = ['embroidery.design', 'advanced.accounts.mixin', 'advanced.accounts.remap.mixin']
    # The thread manufacturer digitising is limited to is an Account.
    _adv_remap = {'adv_digitise_manufacturer_id': 'digitise_manufacturer_id'}

    digitise_manufacturer_id = fields.Many2one(string='Thread Manufacturer (Partner)')
    adv_digitise_manufacturer_id = fields.Many2one(
        'advanced.account', string='Thread Manufacturer', ondelete='set null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='Only match threads by this manufacturer. Leave empty to use every thread.')

    @api.onchange('adv_digitise_manufacturer_id')
    def _onchange_adv_digitise_manufacturer_id(self):
        self._adv_remap_push('adv_digitise_manufacturer_id')


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'advanced.accounts.remap.mixin']
    _adv_remap = {'adv_thread_manufacturer_id': 'thread_manufacturer_id'}

    thread_manufacturer_id = fields.Many2one(string='Thread Manufacturer (Partner)')
    adv_thread_manufacturer_id = fields.Many2one(
        'advanced.account', string='Thread Manufacturer', ondelete='set null',
        compute='_compute_adv_remap', store=True, readonly=False, precompute=True,
        help='The company that makes this thread (e.g. Madeira, Isacord, Brother).')

    @api.onchange('adv_thread_manufacturer_id')
    def _onchange_adv_thread_manufacturer_id(self):
        self._adv_remap_push('adv_thread_manufacturer_id')
