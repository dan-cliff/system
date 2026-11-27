# -*- coding: utf-8 -*-
import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools import formats, raster_tools, svg_tools
from ..tools.formats import OPERATIONS, VECTOR_OPERATIONS, extension

VISUAL_EDITOR_INTERNAL_PARAM = 'laser_jobbing.visual_editor_internal'
VISUAL_EDITOR_PORTAL_PARAM = 'laser_jobbing.visual_editor_portal'
MAX_UPLOAD_PARAM = 'laser_jobbing.max_upload_mb'
DEFAULT_MAX_UPLOAD_MB = 20

ELEMENT_TYPES = [('text', 'Text'), ('image', 'Picture / Artwork')]
TEXT_ALIGN = [('left', 'Left'), ('center', 'Centre'), ('right', 'Right')]
# Template fields whose change means open jobs make their file again.
OUTPUT_TEMPLATE_FIELDS = {
    'operation', 'width_mm', 'height_mm', 'dpi', 'grayscale', 'base_file', 'base_filename', 'element_ids',
}
ELEMENT_OUTPUT_FIELDS = {
    'element_type', 'x_mm', 'y_mm', 'width_mm', 'height_mm', 'default_text', 'max_length', 'multiline',
    'font_id', 'font_size_mm', 'auto_fit', 'text_align', 'color', 'image_fit', 'default_image',
    'default_image_filename', 'sequence',
}
IMAGE_FIT = [('contain', 'Fit inside the box'), ('cover', 'Fill the box (crop)')]


def binary_bytes(record, field_name):
    """Raw bytes of a Binary field (whatever bin_size the context asks for)."""
    value = record.with_context(bin_size=False)[field_name]
    return base64.b64decode(value) if value else None


def param_enabled(env, key):
    return env['ir.config_parameter'].sudo().get_param(key) in ('True', 'true', '1')


class LaserTemplate(models.Model):
    """A base design with variable elements (text and pictures) to personalise."""
    _name = 'laser.template'
    _description = 'Laser Template'
    _inherit = ['mail.thread']
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company, tracking=True,
        help='Leave empty to share the template with every company.',
    )
    operation = fields.Selection(
        OPERATIONS, string='Operation', required=True, default='engrave', tracking=True,
        help='Cutting and scoring produce an .svg file; engraving produces a picture in the format '
             'of the picture uploaded (png, jpg, jpeg, bmp, webp, tif, tiff, gif or heic).',
    )
    description = fields.Html(string='Notes')
    width_mm = fields.Float(string='Width (mm)', digits=(16, 2), required=True, default=100.0, tracking=True)
    height_mm = fields.Float(string='Height (mm)', digits=(16, 2), required=True, default=100.0, tracking=True)
    dpi = fields.Integer(
        string='Resolution (dpi)', default=300,
        help='Dots per inch of the engraving picture a job produces.',
    )
    grayscale = fields.Boolean(
        string='Greyscale', default=True,
        help='Turn engraving pictures to greys, as the laser engraves light and dark.',
    )
    material_id = fields.Many2one('laser.material', string='Material', tracking=True)
    base_file = fields.Binary(
        string='Base File', attachment=True,
        help='The design the variable elements are placed on: an .svg for cutting and scoring, '
             'a picture for engraving. It is scaled to fit the template size.',
    )
    base_filename = fields.Char(string='Base File Name', tracking=True)
    base_format = fields.Char(string='Base Format', compute='_compute_base_format', store=True)
    element_ids = fields.One2many('laser.template.element', 'template_id', string='Variable Elements', copy=True)
    element_count = fields.Integer(compute='_compute_counts')
    customer_element_count = fields.Integer(
        compute='_compute_counts',
        help='Elements the customer fills in on the website.',
    )
    product_tmpl_ids = fields.One2many('product.template', 'laser_template_id', string='Products')
    product_count = fields.Integer(compute='_compute_counts')
    job_ids = fields.One2many('laser.job', 'template_id', string='Jobs')
    job_count = fields.Integer(compute='_compute_counts')
    output_format_info = fields.Char(string='Job File', compute='_compute_output_format_info')
    laser_visual_editor = fields.Boolean(compute='_compute_laser_visual_editor')

    @api.depends('base_filename')
    def _compute_base_format(self):
        for template in self:
            template.base_format = extension(template.base_filename) or False

    def _compute_counts(self):
        for template in self:
            template.element_count = len(template.element_ids)
            template.customer_element_count = len(template.element_ids.filtered('customer_editable'))
            template.product_count = len(template.with_context(active_test=False).product_tmpl_ids)
            template.job_count = self.env['laser.job'].search_count([('template_id', '=', template.id)])

    @api.depends('operation')
    def _compute_output_format_info(self):
        for template in self:
            if template.operation in VECTOR_OPERATIONS:
                template.output_format_info = _('.svg file')
            else:
                template.output_format_info = _('Picture in the format uploaded (png, jpg, jpeg, bmp, '
                                                'webp, tif, tiff, gif or heic)')

    def _compute_laser_visual_editor(self):
        enabled = param_enabled(self.env, VISUAL_EDITOR_INTERNAL_PARAM)
        for template in self:
            template.laser_visual_editor = enabled

    @api.constrains('width_mm', 'height_mm', 'dpi')
    def _check_size(self):
        for template in self:
            if template.width_mm <= 0 or template.height_mm <= 0:
                raise ValidationError(_('The template\'s width and height must be more than 0 mm.'))
            if template.operation == 'engrave' and not 25 <= template.dpi <= 2400:
                raise ValidationError(_('The resolution must be between 25 and 2400 dpi.'))

    @api.constrains('base_file', 'base_filename', 'operation')
    def _check_base_file(self):
        for template in self:
            if not template.base_file:
                continue
            ext = extension(template.base_filename)
            allowed = formats.allowed_extensions(template.operation)
            if ext not in allowed:
                raise ValidationError(_(
                    'The base file of a %(operation)s template must be one of: %(formats)s.',
                    operation=dict(OPERATIONS)[template.operation].lower(),
                    formats=', '.join('.%s' % e for e in allowed),
                ))
            data = binary_bytes(template, 'base_file')
            try:
                if ext == 'svg':
                    svg_tools.parse_svg(data)
                elif ext != 'heic' or raster_tools.HEIF_SUPPORTED:
                    raster_tools.open_image(data)
            except (svg_tools.SvgError, raster_tools.RasterError) as error:
                raise ValidationError(str(error)) from error

    @api.onchange('base_file', 'base_filename')
    def _onchange_base_file_size(self):
        """Take the template size from the base file when it states one."""
        if not self.base_file or not self.base_filename:
            return
        ext = extension(self.base_filename)
        try:
            data = base64.b64decode(self.base_file)
            if ext == 'svg':
                size = svg_tools.size_mm(svg_tools.parse_svg(data))
            elif ext in formats.RASTER_EXTENSIONS and (ext != 'heic' or raster_tools.HEIF_SUPPORTED):
                (width, height), dpi = raster_tools.image_size(data)
                dpi = dpi or self.dpi or 300
                size = (width * 25.4 / dpi, height * 25.4 / dpi)
            else:
                size = None
        except Exception:  # noqa: BLE001 - the constraint explains a bad file on save
            return
        if size:
            self.width_mm, self.height_mm = round(size[0], 2), round(size[1], 2)

    def write(self, vals):
        # Element changes saved with the template refresh the jobs once, below.
        res = super(LaserTemplate, self.with_context(laser_skip_refresh=True)).write(vals)
        if OUTPUT_TEMPLATE_FIELDS & set(vals):
            self._laser_refresh_open_jobs()
        return res

    def _laser_refresh_open_jobs(self):
        """Open jobs follow their template: same elements, file made again."""
        if self.env.context.get('laser_skip_refresh') or not self:
            return
        jobs = self.env['laser.job'].sudo().search([
            ('template_id', 'in', self.ids), ('state', 'in', ('draft', 'confirmed')),
        ])
        jobs._sync_values()
        jobs._generate_output_quietly()

    # ── Actions ──────────────────────────────────────────────────────────
    def action_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('laser_jobbing.action_laser_job')
        action.update({'domain': [('template_id', '=', self.id)], 'context': {'default_template_id': self.id}})
        return action

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Products'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('laser_template_id', '=', self.id)],
            'context': {'default_laser_template_id': self.id},
        }

    # ── Editor data ──────────────────────────────────────────────────────
    def _base_url(self):
        self.ensure_one()
        if not self.base_file:
            return ''
        return '/laser_jobbing/template/%s/base?unique=%s' % (
            self.id, int(self.write_date.timestamp()) if self.write_date else 0,
        )

    def laser_editor_data(self, customer_only=False):
        """What the visual editors need to draw the template (JSON)."""
        self.ensure_one()
        template = self.sudo()
        elements = template.element_ids
        if customer_only:
            elements = elements.filtered('customer_editable')
        return {
            'id': template.id,
            'name': template.name,
            'operation': template.operation,
            'width': template.width_mm,
            'height': template.height_mm,
            'base_url': template._base_url(),
            'accept': formats.accept_attribute(template.operation),
            'elements': [element._editor_data() for element in elements],
            'fixed_elements': [
                element._editor_data() for element in template.element_ids - elements
            ],
        }

    def _check_upload(self, filename, label):
        """Raise when a file can't be used by the template's operation."""
        self.ensure_one()
        allowed = formats.allowed_extensions(self.operation)
        if extension(filename) not in allowed:
            raise ValidationError(_(
                '"%(label)s" must be one of: %(formats)s.',
                label=label, formats=', '.join('.%s' % e for e in allowed),
            ))

    def _laser_public_access(self):
        """Whether anyone may see this template's base file and fonts (see the website bridge)."""
        return False


class LaserTemplateElement(models.Model):
    """A variable part of a template: a text or a picture filled in for each job."""
    _name = 'laser.template.element'
    _description = 'Laser Template Element'
    _order = 'sequence, id'

    template_id = fields.Many2one('laser.template', required=True, ondelete='cascade', index=True)
    operation = fields.Selection(related='template_id.operation')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Label', required=True, translate=True,
                       help='What the element is called, e.g. "Name" or "Your photo".')
    key = fields.Char(
        string='Key', help='Technical name of the element, used in imports and exports. '
                           'Filled in from the label.',
    )
    element_type = fields.Selection(ELEMENT_TYPES, string='Type', required=True, default='text')
    required = fields.Boolean(default=True)
    customer_editable = fields.Boolean(
        string='Customer Fills In', default=True,
        help='Customers fill this in on the website. Other elements keep their default and only '
             'employees change them.',
    )
    help_text = fields.Char(string='Hint', translate=True, help='Shown under the field, e.g. "Up to 12 letters".')

    x_mm = fields.Float(string='X (mm)', digits=(16, 2), default=0.0)
    y_mm = fields.Float(string='Y (mm)', digits=(16, 2), default=0.0)
    width_mm = fields.Float(string='Width (mm)', digits=(16, 2), default=50.0)
    height_mm = fields.Float(string='Height (mm)', digits=(16, 2), default=15.0)

    # Text
    default_text = fields.Text(string='Default Text', translate=True)
    max_length = fields.Integer(string='Max. Characters', help='0 for no limit.')
    multiline = fields.Boolean(string='Several Lines')
    font_id = fields.Many2one('laser.font', string='Font')
    font_size_mm = fields.Float(string='Font Size (mm)', digits=(16, 2), default=8.0)
    auto_fit = fields.Boolean(string='Shrink to Fit', default=True,
                              help='Make the text smaller when it doesn\'t fit the box.')
    text_align = fields.Selection(TEXT_ALIGN, string='Alignment', default='center', required=True)
    color = fields.Char(string='Colour', default='#000000',
                        help='Engraving: the text colour. Cutting and scoring: the line colour, which laser '
                             'software can use to pick the operation.')

    # Picture
    image_fit = fields.Selection(IMAGE_FIT, string='Fit', default='contain', required=True)
    default_image = fields.Binary(string='Default Picture / Artwork', attachment=True)
    default_image_filename = fields.Char()

    @api.constrains('width_mm', 'height_mm', 'font_size_mm')
    def _check_box(self):
        for element in self:
            if element.width_mm <= 0 or element.height_mm <= 0:
                raise ValidationError(_('The width and height of "%s" must be more than 0 mm.', element.name))
            if element.element_type == 'text' and element.font_size_mm <= 0:
                raise ValidationError(_('The font size of "%s" must be more than 0 mm.', element.name))

    @api.constrains('default_image', 'default_image_filename')
    def _check_default_image(self):
        for element in self:
            if element.default_image:
                element.template_id._check_upload(element.default_image_filename, element.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key') and vals.get('name'):
                vals['key'] = self._make_key(vals['name'])
        elements = super().create(vals_list)
        elements.template_id._laser_refresh_open_jobs()
        return elements

    def write(self, vals):
        if 'key' in vals and not vals['key'] and 'name' in vals:
            vals['key'] = self._make_key(vals['name'])
        res = super().write(vals)
        if ELEMENT_OUTPUT_FIELDS & set(vals):
            self.template_id._laser_refresh_open_jobs()
        return res

    def unlink(self):
        templates = self.template_id
        res = super().unlink()
        templates.exists()._laser_refresh_open_jobs()
        return res

    @api.model
    def _make_key(self, name):
        return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_') or 'element'

    def _editor_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'key': self.key or '',
            'name': self.name,
            'type': self.element_type,
            'required': self.required,
            'help': self.help_text or '',
            'x': self.x_mm,
            'y': self.y_mm,
            'w': self.width_mm,
            'h': self.height_mm,
            'default_text': self.default_text or '',
            'max_length': self.max_length,
            'multiline': self.multiline,
            'font_family': (self.font_id.css_family or 'sans-serif') if self.font_id else 'sans-serif',
            'font_name': self.font_id.name or '',
            'font_url': self.font_id._font_url() if self.font_id else '',
            'font_id': self.font_id.id,
            'font_size': self.font_size_mm,
            'auto_fit': self.auto_fit,
            'align': self.text_align,
            'color': svg_tools.safe_color(self.color),
            'fit': self.image_fit,
            'default_image_url': (
                '/laser_jobbing/element/%s/image?unique=%s' % (
                    self.id, int(self.write_date.timestamp()) if self.write_date else 0)
                if self.default_image else ''
            ),
        }


def max_upload_bytes(env):
    value = env['ir.config_parameter'].sudo().get_param(MAX_UPLOAD_PARAM)
    try:
        value = int(value or DEFAULT_MAX_UPLOAD_MB)
    except ValueError:
        value = DEFAULT_MAX_UPLOAD_MB
    return max(value, 1) * 1024 * 1024
