# -*- coding: utf-8 -*-
import base64
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..lib import digitise, pes

_logger = logging.getLogger(__name__)

# Changing any of these re-digitises the artwork.
DIGITISE_FIELDS = (
    'artwork_file', 'digitise_width_mm', 'digitise_height_mm', 'digitise_max_colors',
    'digitise_row_spacing', 'digitise_stitch_length', 'digitise_fill_angle',
    'digitise_underlay', 'digitise_remove_background', 'digitise_min_area',
    'digitise_manufacturer_id', 'digitise_thread_type_ids',
)


class EmbroideryDesign(models.Model):
    """A Brother .pes design: uploaded, or digitised from artwork."""
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
    design_file = fields.Binary(
        string='Design File (.pes)', attachment=True,
        help='The Brother .pes file the machines stitch. Upload one, or upload artwork and '
             'it is digitised into this file.')
    design_filename = fields.Char(string='File Name')
    note = fields.Html(string='Notes')

    # ── Digitising from artwork ───────────────────────────────────────────
    artwork_file = fields.Binary(
        string='Artwork', attachment=True,
        help='A PNG, JPG or SVG picture. It is digitised into the .pes design file as soon as '
             'it is saved, with its colours matched to your thread products.')
    artwork_filename = fields.Char(string='Artwork File Name')
    is_digitised = fields.Boolean(compute='_compute_is_digitised', string='Digitised from Artwork')
    digitise_width_mm = fields.Float(
        string='Stitched Width (mm)', digits=(16, 1), default=80.0,
        help='How wide the stitched design is. The height follows the artwork\'s proportions.')
    digitise_height_mm = fields.Float(
        string='Max Height (mm)', digits=(16, 1),
        help='Optional: the design is made smaller if it would be taller than this.')
    digitise_max_colors = fields.Integer(
        string='Max Thread Colours', default=6,
        help='The most thread colours to use. Smaller colour areas join the nearest colour kept.')
    digitise_row_spacing = fields.Float(
        string='Fill Row Spacing (mm)', digits=(16, 2), default=0.4,
        help='Distance between fill rows. Smaller is denser: 0.4 mm suits most fabrics, '
             '0.5 mm is lighter for thin fabrics.')
    digitise_stitch_length = fields.Float(
        string='Fill Stitch Length (mm)', digits=(16, 1), default=3.5,
        help='The longest stitch in a fill row.')
    digitise_fill_angle = fields.Float(
        string='Fill Angle (°)', digits=(16, 0), default=45.0,
        help='Direction of the fill rows, in degrees anticlockwise from horizontal.')
    digitise_underlay = fields.Boolean(
        string='Underlay', default=True,
        help='Stitch a light fill across each area first, so the top stitches sit flat.')
    digitise_remove_background = fields.Boolean(
        string='Remove Background', default=True,
        help='Leave out the background: transparent pixels, and for pictures without '
             'transparency the colour around the edge.')
    digitise_min_area = fields.Float(
        string='Smallest Colour Area (mm²)', digits=(16, 1), default=3.0,
        help='Colours covering less than this are given to the nearest colour kept.')
    digitise_manufacturer_id = fields.Many2one(
        'res.partner', string='Thread Manufacturer', domain=[('is_company', '=', True)],
        help='Only match threads by this manufacturer. Leave empty to use every thread.')
    digitise_thread_type_ids = fields.Many2many(
        'embroidery.thread.type', string='Thread Types',
        help='Only match threads of these types. Leave empty to use every type.')
    thread_catalogue_count = fields.Integer(
        compute='_compute_thread_catalogue_count', string='Threads to Match')

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
    color_ids = fields.One2many('embroidery.design.color', 'design_id', string='Thread Colours')
    size_display = fields.Char(string='Size', compute='_compute_size_display')
    job_count = fields.Integer(compute='_compute_job_count', string='Jobs')

    @api.depends('width_mm', 'height_mm')
    def _compute_size_display(self):
        for design in self:
            design.size_display = '%.1f x %.1f mm' % (design.width_mm, design.height_mm) if design.stitch_count else ''

    @api.depends('artwork_file')
    def _compute_is_digitised(self):
        for design in self:
            design.is_digitised = bool(design.artwork_file)

    @api.depends('digitise_manufacturer_id', 'digitise_thread_type_ids', 'company_id')
    def _compute_thread_catalogue_count(self):
        Product = self.env['product.product']
        for design in self:
            design.thread_catalogue_count = len(Product._embroidery_thread_catalogue(
                design.digitise_manufacturer_id, design.digitise_thread_type_ids, design.company_id))

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

    @api.onchange('artwork_filename')
    def _onchange_artwork_filename(self):
        if self.artwork_filename and not self.name:
            self.name = self.artwork_filename.rsplit('.', 1)[0]

    @api.constrains('design_filename')
    def _check_filename(self):
        for design in self:
            if design.design_filename and not design.design_filename.lower().endswith('.pes'):
                raise ValidationError(_('"%s" is not a .pes file. Save the design as Brother .pes and upload that.',
                                        design.design_filename))

    @api.constrains('artwork_filename')
    def _check_artwork_filename(self):
        for design in self:
            name = (design.artwork_filename or '').lower()
            if name and not name.endswith(digitise.ARTWORK_EXTENSIONS):
                raise ValidationError(_('"%s" is not a PNG, JPG or SVG picture.', design.artwork_filename))

    @api.constrains('digitise_width_mm', 'digitise_height_mm', 'digitise_max_colors',
                    'digitise_row_spacing', 'digitise_stitch_length')
    def _check_digitise_settings(self):
        for design in self:
            if design.digitise_width_mm < 0 or design.digitise_height_mm < 0:
                raise ValidationError(_('The width and height cannot be negative.'))
            if not 1 <= design.digitise_max_colors <= 30:
                raise ValidationError(_('Max Thread Colours must be between 1 and 30.'))
            if not 0.25 <= design.digitise_row_spacing <= 2.0:
                raise ValidationError(_('Fill Row Spacing must be between 0.25 and 2 mm.'))
            if not 1.0 <= design.digitise_stitch_length <= 7.0:
                raise ValidationError(_('Fill Stitch Length must be between 1 and 7 mm.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                filename = vals.get('design_filename') if vals.get('design_file') else None
                filename = filename or (vals.get('artwork_filename') if vals.get('artwork_file') else None)
                if filename:
                    vals['name'] = filename.rsplit('.', 1)[0]
        designs = super().create(vals_list)
        from_artwork = designs.filtered('artwork_file')
        from_artwork._digitise()
        (designs - from_artwork)._read_design_file()
        designs._check_has_design()
        return designs

    def write(self, vals):
        if self.env.context.get('embroidery_design_internal'):
            return super().write(vals)
        if 'design_file' in vals and 'artwork_file' not in vals and vals.get('design_file'):
            # A .pes uploaded over a digitised design replaces it: forget the artwork.
            vals = dict(vals, artwork_file=False, artwork_filename=False)
        res = super(EmbroideryDesign, self.with_context(embroidery_color_batch=True)).write(vals)
        redigitise = self.filtered('artwork_file') if any(f in vals for f in DIGITISE_FIELDS) else self.browse()
        redigitise._digitise()
        if 'design_file' in vals:
            (self - redigitise)._read_design_file()
        elif 'color_ids' in vals:
            self._apply_thread_choices()
        if {'design_file', 'artwork_file'} & set(vals):
            self._check_has_design()
        return res

    def _check_has_design(self):
        for design in self:
            if not design.design_file:
                raise ValidationError(_('Upload a .pes design file, or a PNG, JPG or SVG picture to digitise.'))

    def _internal_write(self, values):
        return super(EmbroideryDesign, self.with_context(embroidery_design_internal=True)).write(values)

    # ── Digitising ────────────────────────────────────────────────────────

    def _digitise_settings(self):
        self.ensure_one()
        return digitise.Settings(
            width_mm=self.digitise_width_mm,
            height_mm=self.digitise_height_mm,
            max_colors=self.digitise_max_colors,
            row_spacing_mm=self.digitise_row_spacing,
            stitch_length_mm=self.digitise_stitch_length,
            fill_angle=self.digitise_fill_angle,
            underlay=self.digitise_underlay,
            remove_background=self.digitise_remove_background,
            min_area_mm2=self.digitise_min_area,
        )

    def _digitise(self):
        """Digitise the artwork into the .pes design file, matching its colours
        to the thread products (Brother's palette when there are none)."""
        for design in self:
            if not design.artwork_file:
                continue
            products = self.env['product.product']._embroidery_thread_catalogue(
                design.digitise_manufacturer_id, design.digitise_thread_type_ids, design.company_id)
            threads = [product._embroidery_thread_info() for product in products]
            data = base64.b64decode(design.with_context(bin_size=False).artwork_file)
            try:
                result = digitise.digitise(data, design.artwork_filename, threads, design._digitise_settings())
            except (digitise.DigitiseError, pes.PesError) as error:
                raise UserError(_('%(file)s could not be digitised: %(error)s',
                                  file=design.artwork_filename or design.name, error=error))
            label = re.sub(r'[^A-Za-z0-9 _-]', '', design.name or '')[:8] or 'DESIGN'
            base_name = re.sub(r'[\\/:*?"<>|]', '', design.name or '').strip() or 'design'
            design._internal_write({
                'design_file': base64.b64encode(result.pes(label=label)),
                'design_filename': '%s.pes' % base_name,
            })
            design._read_design_file(threads=result.threads, artwork_colors=result.colors)
            if not threads:
                design.message_post(body=_(
                    'Digitised from %(file)s with Brother\'s standard colours: no thread products '
                    'with a Thread Colour were found. Put your threads in a product category that '
                    'includes threads and give them a colour to match them instead.',
                    file=design.artwork_filename or _('the artwork')))
            else:
                design.message_post(body=_(
                    'Digitised from %(file)s: %(colours)s thread colours, %(stitches)s stitches.',
                    file=design.artwork_filename or _('the artwork'),
                    colours=design.color_count, stitches=design.stitch_count))

    def action_digitise(self):
        """Digitise the artwork again (e.g. after changing the thread products)."""
        designs = self.filtered('artwork_file')
        if not designs:
            raise UserError(_('Upload a PNG, JPG or SVG picture to digitise first.'))
        designs._digitise()
        return True

    def _apply_thread_choices(self):
        """Rewrite a digitised design's .pes file when a colour line was given
        a different thread product, so the file carries the thread's colour."""
        for design in self.filtered('artwork_file'):
            lines = design.color_ids.sorted('sequence')
            if not any(line.product_id and (line.product_id.thread_color or '') != (line.color_hex or '')
                       for line in lines):
                continue
            data = base64.b64decode(design.with_context(bin_size=False).design_file)
            read = pes.read_pes(data)
            blocks = [[]]
            for command in read.commands:
                if command[2] == pes.COLOR:
                    blocks.append([])
                else:
                    blocks[-1].append(command)
            if len(blocks) != len(lines):
                raise UserError(_('The thread colours of %s no longer match its design file. '
                                  'Digitise it again.', design.name))
            threads = [line.product_id._embroidery_thread_info() if line.product_id and line.product_id.thread_color
                       else {'name': line.name, 'hex': line.color_hex, 'catalog': '', 'brand': ''}
                       for line in lines]
            design._internal_write({
                'design_file': base64.b64encode(pes.write_pes(blocks, threads, label=read.label)),
            })
            design._read_design_file(threads=threads, artwork_colors=lines.mapped('artwork_color_hex'))

    # ── Reading the file ──────────────────────────────────────────────────

    def _read_design_file(self, threads=None, artwork_colors=None):
        """Fill the stitch details, colours and preview from the .pes file.
        ``threads`` / ``artwork_colors`` (one per colour block) link the colour
        lines to their thread products and the artwork colour they stand for."""
        for design in self:
            if not design.design_file:
                continue
            data = base64.b64decode(design.with_context(bin_size=False).design_file)
            try:
                result = pes.read_pes(data)
            except pes.PesError as error:
                raise ValidationError(_('%(file)s could not be read: %(error)s',
                                        file=design.design_filename or design.name, error=error))
            lines = []
            for number, color in enumerate(result.colors, start=1):
                line = {
                    'sequence': number,
                    'palette_index': color['index'],
                    'name': color['name'],
                    'color_hex': color['hex'],
                    'stitch_count': color['stitches'],
                }
                thread = threads[number - 1] if threads and number <= len(threads) else {}
                if thread.get('product_id'):
                    line['product_id'] = thread['product_id']
                artwork = artwork_colors[number - 1] if artwork_colors and number <= len(artwork_colors) else None
                if artwork:
                    line['artwork_color_hex'] = artwork
                    artwork_rgb, thread_rgb = digitise.hex_to_rgb(artwork), digitise.hex_to_rgb(color['hex'])
                    if artwork_rgb and thread_rgb:
                        line['color_difference'] = digitise.delta_e(
                            digitise.rgb_to_lab(artwork_rgb), digitise.rgb_to_lab(thread_rgb))
                lines.append(fields.Command.create(line))
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
                'color_ids': [fields.Command.clear()] + lines,
            }
            try:
                values['image_1920'] = base64.b64encode(result.preview_png())
            except Exception:  # the details are still useful without a preview
                _logger.exception('Could not draw the preview of embroidery design %s', design.id)
            design._internal_write(values)

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
    sequence = fields.Integer(string='#', readonly=True)
    palette_index = fields.Integer(string='Brother Colour No.', readonly=True)
    name = fields.Char(string='Thread Colour', readonly=True)
    color_hex = fields.Char(string='Colour', readonly=True)
    stitch_count = fields.Integer(string='Stitches', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Thread', domain=[('is_thread', '=', True)], ondelete='set null',
        help='The thread product stitched in this colour. On a design digitised from artwork, '
             'picking another thread rewrites the design file with its colour.')
    artwork_color_hex = fields.Char(string='Artwork Colour', readonly=True,
                                    help='The colour in the artwork this thread stands for.')
    color_difference = fields.Float(
        string='Colour Difference', digits=(16, 1), readonly=True,
        help='How far the thread is from the artwork colour (CIEDE2000): under 2 is hard to see, '
             'under 5 is close, over 10 is clearly different. Add a closer thread product, or '
             'pick another thread, to bring it down.')

    def write(self, vals):
        res = super().write(vals)
        if 'product_id' in vals and not self.env.context.get('embroidery_color_batch') \
                and not self.env.context.get('embroidery_design_internal'):
            self.design_id._apply_thread_choices()
        return res
