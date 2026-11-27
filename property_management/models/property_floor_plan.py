# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models
from odoo.tools.mimetypes import guess_mimetype


class PropertyFloorPlan(models.Model):
    _name = 'property.floor.plan'
    _description = 'Property Floor Plan'
    _order = 'property_id, sequence, id'

    property_id = fields.Many2one('property.property', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='property_id.company_id', store=True)
    name = fields.Char(required=True, help='e.g. "Ground Floor" or "Level 2 – Fit-out".')
    sequence = fields.Integer(default=10)
    plan_file = fields.Binary(string='Floor Plan', required=True, attachment=True)
    plan_file_name = fields.Char(string='File Name')
    file_kind = fields.Selection(
        [('pdf', 'PDF'), ('image', 'Image'), ('other', 'Other')], string='File Type',
        compute='_compute_file_kind', store=True,
        help='Decides how the plan is previewed. Worked out from the uploaded file.',
    )
    plan_image = fields.Binary(compute='_compute_preview', string='Preview')
    plan_pdf = fields.Binary(compute='_compute_preview', string='PDF Preview')
    area = fields.Float(string='Area (m²)', digits=(16, 2))
    revision_date = fields.Date(string='Drawn On')
    notes = fields.Text()

    @api.depends('plan_file')
    def _compute_file_kind(self):
        for plan in self:
            raw = plan.with_context(bin_size=False).plan_file
            if not raw:
                plan.file_kind = False
                continue
            mimetype = guess_mimetype(base64.b64decode(raw[:1024 * 4]))
            if mimetype == 'application/pdf':
                plan.file_kind = 'pdf'
            elif mimetype.startswith('image/'):
                plan.file_kind = 'image'
            else:
                plan.file_kind = 'other'

    @api.depends('plan_file', 'file_kind')
    def _compute_preview(self):
        for plan in self:
            data = plan.with_context(bin_size=False).plan_file
            plan.plan_image = data if plan.file_kind == 'image' else False
            plan.plan_pdf = data if plan.file_kind == 'pdf' else False
