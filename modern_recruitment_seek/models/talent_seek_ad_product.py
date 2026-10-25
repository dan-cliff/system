# -*- coding: utf-8 -*-
from odoo import fields, models


class TalentSeekAdProduct(models.Model):
    """The ad products SEEK offers for a job position (fetched for each job,
    as SEEK's offer and prices depend on the ad)."""
    _name = 'talent.seek.ad.product'
    _description = 'SEEK Ad Product'
    _order = 'sequence, id'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    seek_id = fields.Char(string='SEEK ID', required=True)
    name = fields.Char(string='Ad Product', required=True)
    price = fields.Char(string='Price')
    description = fields.Text(string='Description')

    def _compute_display_name(self):
        for product in self:
            product.display_name = '%s (%s)' % (product.name, product.price) if product.price else product.name
