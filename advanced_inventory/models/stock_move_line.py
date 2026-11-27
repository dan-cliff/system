# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    # Detailed operations follow the walk through the warehouse.
    _order = 'walk_sequence, result_package_id desc, id'

    walk_sequence = fields.Integer(
        string='Walk Order', compute='_compute_walk_sequence', store=True, index=True,
        help='Where this line is on the walk through the warehouse: the location the product is '
             'picked from, or for put-away (into a storage location) the location it goes to.')
    walk_location_id = fields.Many2one(
        'stock.location', string='Walk To', compute='_compute_walk_sequence', store=True,
        help='The location the picker walks to for this line.')

    @api.depends('location_id', 'location_dest_id', 'location_id.walk_sequence',
                 'location_dest_id.walk_sequence', 'location_id.storage_level',
                 'location_dest_id.storage_level', 'location_id.usage')
    def _compute_walk_sequence(self):
        for line in self:
            location = line._walk_location()
            line.walk_location_id = location
            line.walk_sequence = location.walk_sequence

    def _walk_location(self):
        """Picking walks to where the product is taken from; put-away walks to
        where it is stored. A line is a put-away when it goes into a layout
        location from somewhere that isn't one (a receipt, an input area)."""
        self.ensure_one()
        source, dest = self.location_id, self.location_dest_id
        if dest.storage_level and not source.storage_level:
            return dest
        if source.usage == 'internal':
            return source
        return dest
