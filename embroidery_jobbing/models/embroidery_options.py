# -*- coding: utf-8 -*-
"""Option lists managed under Embroidery > Configuration."""
from odoo import api, fields, models


class EmbroideryMachineModel(models.Model):
    _name = 'embroidery.machine.model'
    _description = 'Embroidery Machine Model'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    manufacturer = fields.Char()
    needle_count = fields.Integer(string='Needles', default=1)
    max_speed_spm = fields.Integer(
        string='Max Speed (spm)',
        help='Fastest the machine can stitch, in stitches per minute.',
    )
    max_width_mm = fields.Float(string='Max Width (mm)', help='Widest design the machine can stitch.')
    max_height_mm = fields.Float(string='Max Height (mm)', help='Tallest design the machine can stitch.')
    hoop_ids = fields.Many2many(
        'embroidery.hoop',
        string='Hoops & Frames',
        help='Hoops and frames that fit this model. New machines of this model start with them.',
    )


class EmbroideryHoop(models.Model):
    _name = 'embroidery.hoop'
    _description = 'Embroidery Hoop / Frame'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    width_mm = fields.Float(string='Sewing Width (mm)')
    height_mm = fields.Float(string='Sewing Height (mm)')

    @api.depends('name', 'width_mm', 'height_mm')
    def _compute_display_name(self):
        for hoop in self:
            if hoop.width_mm and hoop.height_mm:
                hoop.display_name = '%s (%g x %g mm)' % (hoop.name, hoop.width_mm, hoop.height_mm)
            else:
                hoop.display_name = hoop.name

    def _fits(self, width_mm, height_mm):
        """Whether a design of this size fits the hoop, either way round."""
        self.ensure_one()
        if not (self.width_mm and self.height_mm):
            return True
        return (width_mm <= self.width_mm and height_mm <= self.height_mm) or (
            width_mm <= self.height_mm and height_mm <= self.width_mm
        )


class EmbroideryPlacement(models.Model):
    _name = 'embroidery.placement'
    _description = 'Embroidery Placement'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class EmbroideryStabiliser(models.Model):
    _name = 'embroidery.stabiliser'
    _description = 'Embroidery Stabiliser / Backing'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
