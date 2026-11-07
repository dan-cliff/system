# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.formats import FONT_EXTENSIONS, extension


class LaserFont(models.Model):
    """A font that text elements can use (Configuration › Laser Fonts)."""
    _name = 'laser.font'
    _description = 'Laser Font'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    font_file = fields.Binary(
        string='Font File', attachment=True,
        help='A .ttf or .otf file. It is used to draw engraving text, to turn cutting and scoring text '
             'into outlines and to show the text in the visual editors. Without a file the font family '
             'below is used.',
    )
    font_filename = fields.Char(string='Font File Name')
    css_family = fields.Char(
        string='Font Family', default='sans-serif', required=True,
        help='The family written into .svg files and used in previews when there is no font file '
             '(e.g. "Arial", "serif").',
    )

    @api.constrains('font_file', 'font_filename')
    def _check_font_file(self):
        for font in self:
            if font.font_file and extension(font.font_filename) not in FONT_EXTENSIONS:
                raise ValidationError(_('Fonts must be .ttf or .otf files.'))

    def _font_data(self):
        """The font file's bytes, or None."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id), ('res_field', '=', 'font_file'),
        ], limit=1)
        return attachment.raw if attachment else None

    def _font_url(self):
        self.ensure_one()
        if not self.font_file:
            return ''
        return '/laser_jobbing/font/%s?unique=%s' % (
            self.id, int(self.write_date.timestamp()) if self.write_date else 0,
        )


class LaserMaterial(models.Model):
    """A material laser jobs are made from (Configuration › Laser Materials)."""
    _name = 'laser.material'
    _description = 'Laser Material'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    thickness_mm = fields.Float(string='Thickness (mm)', digits=(16, 2))
    machine_settings = fields.Text(
        string='Machine Settings',
        help='Power, speed, passes and focus for this material, shown to whoever runs the job.',
    )
