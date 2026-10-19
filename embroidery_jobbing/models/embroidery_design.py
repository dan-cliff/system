# -*- coding: utf-8 -*-
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..lib import pes

_logger = logging.getLogger(__name__)


class EmbroideryDesign(models.Model):
    """A Brother .pes design, read when it is uploaded."""
    _name = 'embroidery.design'
    _description = 'Embroidery Design'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, tracking=True,
    )
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True,
                                 help='The customer this design belongs to, if any.')
    design_file = fields.Binary(string='Design File (.pes)', attachment=True, required=True)
    design_filename = fields.Char(string='File Name')
    note = fields.Html(string='Notes')

    # ── Read from the file ────────────────────────────────────────────────
    stitch_count = fields.Integer(string='Stitches', readonly=True)
    color_count = fields.Integer(string='Colours', readonly=True)
    color_change_count = fields.Integer(string='Colour Changes', readonly=True)
    trim_count = fields.Integer(string='Trims', readonly=True)
    jump_count = fields.Integer(string='Jumps', readonly=True)
    width_mm = fields.Float(string='Width (mm)', digits=(16, 1), readonly=True)
    height_mm = fields.Float(string='Height (mm)', digits=(16, 1), readonly=True)
    pes_version = fields.Char(string='PES Version', readonly=True)
    pes_label = fields.Char(string='Label in File', readonly=True)
    color_ids = fields.One2many('embroidery.design.color', 'design_id', string='Thread Colours', readonly=True)
    size_display = fields.Char(string='Size', compute='_compute_size_display')
    job_count = fields.Integer(compute='_compute_job_count', string='Jobs')

    @api.depends('width_mm', 'height_mm')
    def _compute_size_display(self):
        for design in self:
            design.size_display = '%.1f x %.1f mm' % (design.width_mm, design.height_mm) if design.stitch_count else ''

    def _compute_job_count(self):
        counts = dict(self.env['embroidery.job']._read_group(
            [('design_id', 'in', self.ids)], ['design_id'], ['__count'],
        ))
        for design in self:
            design.job_count = counts.get(design, 0)

    @api.onchange('design_filename')
    def _onchange_design_filename(self):
        if self.design_filename and not self.name:
            self.name = self.design_filename.rsplit('.', 1)[0]

    @api.constrains('design_filename')
    def _check_filename(self):
        for design in self:
            if design.design_filename and not design.design_filename.lower().endswith('.pes'):
                raise ValidationError(_('"%s" is not a .pes file. Save the design as Brother .pes and upload that.',
                                        design.design_filename))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('design_file') and not vals.get('name') and vals.get('design_filename'):
                vals['name'] = vals['design_filename'].rsplit('.', 1)[0]
        designs = super().create(vals_list)
        designs._read_design_file()
        return designs

    def write(self, vals):
        res = super().write(vals)
        if 'design_file' in vals:
            self._read_design_file()
        return res

    def _read_design_file(self):
        """Fill the stitch details, colours and preview from the .pes file."""
        for design in self:
            if not design.design_file:
                continue
            data = base64.b64decode(design.with_context(bin_size=False).design_file)
            try:
                result = pes.read_pes(data)
            except pes.PesError as error:
                raise ValidationError(_('%(file)s could not be read: %(error)s',
                                        file=design.design_filename or design.name, error=error))
            values = {
                'stitch_count': result.stitch_count,
                'color_count': len(result.colors),
                'color_change_count': result.color_change_count,
                'trim_count': result.trim_count,
                'jump_count': result.jump_count,
                'width_mm': result.width_mm,
                'height_mm': result.height_mm,
                'pes_version': result.version,
                'pes_label': result.label,
                'color_ids': [fields.Command.clear()] + [
                    fields.Command.create({
                        'sequence': number,
                        'palette_index': color['index'],
                        'name': color['name'],
                        'color_hex': color['hex'],
                        'stitch_count': color['stitches'],
                    })
                    for number, color in enumerate(result.colors, start=1)
                ],
            }
            try:
                values['image_1920'] = base64.b64encode(result.preview_png())
            except Exception:  # the details are still useful without a preview
                _logger.exception('Could not draw the preview of embroidery design %s', design.id)
            super(EmbroideryDesign, design).write(values)

    def _color_at(self, stitch):
        """(number, colour line) of the colour block the given stitch is in."""
        self.ensure_one()
        done = 0
        colors = self.color_ids.sorted('sequence')
        for number, color in enumerate(colors, start=1):
            done += color.stitch_count
            if stitch < done:
                return number, color
        return len(colors), colors[-1:]

    def action_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_job')
        action['domain'] = [('design_id', '=', self.id)]
        action['context'] = {'default_design_id': self.id}
        return action


class EmbroideryDesignColor(models.Model):
    _name = 'embroidery.design.color'
    _description = 'Embroidery Design Thread Colour'
    _order = 'design_id, sequence'

    design_id = fields.Many2one('embroidery.design', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='#')
    palette_index = fields.Integer(string='Brother Colour No.')
    name = fields.Char(string='Thread Colour')
    color_hex = fields.Char(string='Colour')
    stitch_count = fields.Integer(string='Stitches')
