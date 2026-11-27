# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PropertyPhoto(models.Model):
    _name = 'property.photo'
    _description = 'Property Photo'
    _inherit = ['image.mixin']
    _order = 'property_id, sequence, id'

    property_id = fields.Many2one('property.property', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='property_id.company_id', store=True)
    name = fields.Char(string='Caption')
    sequence = fields.Integer(default=10)
    image_1920 = fields.Image(required=True)
    date_taken = fields.Date(string='Taken On', default=fields.Date.context_today)
    is_cover = fields.Boolean(compute='_compute_is_cover', string='Cover Photo')

    @api.depends('property_id.image_1920', 'image_1920')
    def _compute_is_cover(self):
        for photo in self:
            photo.is_cover = bool(photo.image_1920 and photo.property_id.image_1920
                                  and photo.image_1920 == photo.property_id.image_1920)

    @api.model_create_multi
    def create(self, vals_list):
        photos = super().create(vals_list)
        # The first photo of a property without a cover becomes its cover.
        for photo in photos:
            if not photo.property_id.image_1920:
                photo.property_id.image_1920 = photo.image_1920
        return photos

    def action_set_cover(self):
        self.ensure_one()
        self.property_id.image_1920 = self.image_1920
        return True
