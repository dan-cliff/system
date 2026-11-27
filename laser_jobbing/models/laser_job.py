# -*- coding: utf-8 -*-
import base64
import logging
import re
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import formats, raster_tools, svg_tools
from ..tools.formats import VECTOR_OPERATIONS, extension
from .laser_template import (
    VISUAL_EDITOR_INTERNAL_PARAM, binary_bytes, max_upload_bytes, param_enabled,
)

_logger = logging.getLogger(__name__)

JOB_STATES = [
    ('draft', 'Draft'),
    ('confirmed', 'To Do'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
# Job fields whose change means the file is made again.
OUTPUT_FIELDS = {'template_id', 'value_ids', 'name'}


class LaserJob(models.Model):
    """A personalised piece to cut, score or engrave, and the file the laser runs."""
    _name = 'laser.job'
    _description = 'Laser Job'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_deadline, id desc'
    # Jobs follow the user (or the order they come from), not their template.
    _org_parent_field = False

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'), tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company, tracking=True)
    template_id = fields.Many2one(
        'laser.template', string='Template', required=True, tracking=True, index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    operation = fields.Selection(related='template_id.operation', store=True, string='Operation')
    material_id = fields.Many2one('laser.material', string='Material', tracking=True,
                                  compute='_compute_material_id', store=True, readonly=False)
    machine_settings = fields.Text(related='material_id.machine_settings')
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True, index=True)
    user_id = fields.Many2one('res.users', string='Responsible', tracking=True, index=True,
                              default=lambda self: self.env.user)
    product_id = fields.Many2one(
        'product.product', string='Product', tracking=True,
        domain="[('laser_template_id', '=', template_id)]",
    )
    quantity = fields.Float(string='Quantity', default=1.0, digits='Product Unit', tracking=True)
    state = fields.Selection(JOB_STATES, string='Status', default='draft', required=True, copy=False,
                             tracking=True, index=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Urgent')], default='0')
    date_deadline = fields.Datetime(string='Due At', tracking=True)
    date_done = fields.Datetime(string='Done At', readonly=True, copy=False)
    origin = fields.Char(string='Source Document', copy=False,
                         help='The order this job comes from, e.g. a sales order.')
    notes = fields.Html(string='Notes')
    source = fields.Selection([('backend', 'Backend'), ('website', 'Website')], default='backend',
                              required=True, readonly=True, copy=False)
    access_token = fields.Char(copy=False, readonly=True, default=lambda self: uuid.uuid4().hex)
    value_ids = fields.One2many('laser.job.value', 'job_id', string='Personalisation', copy=True)
    color = fields.Integer(string='Colour')

    # ── The file for the laser ───────────────────────────────────────────
    output_file = fields.Binary(string='Laser File', attachment=True, copy=False, readonly=True)
    output_filename = fields.Char(string='File Name', copy=False, readonly=True)
    output_format = fields.Char(string='Format', copy=False, readonly=True)
    output_date = fields.Datetime(string='File Made At', copy=False, readonly=True)
    output_error = fields.Text(string='File Problem', copy=False, readonly=True)
    preview_url = fields.Char(compute='_compute_preview_url')
    laser_visual_editor = fields.Boolean(compute='_compute_laser_visual_editor')
    personalisation_summary = fields.Text(string='Personalisation Summary', compute='_compute_summary')

    @api.depends('template_id')
    def _compute_material_id(self):
        for job in self:
            job.material_id = job.template_id.material_id or job.material_id

    @api.depends('output_file', 'output_date')
    def _compute_preview_url(self):
        for job in self:
            job.preview_url = '/laser_jobbing/job/%s/preview?unique=%s' % (
                job.id, int(job.output_date.timestamp()),
            ) if job.id and job.output_date and job.output_format else False

    def _compute_laser_visual_editor(self):
        enabled = param_enabled(self.env, VISUAL_EDITOR_INTERNAL_PARAM)
        for job in self:
            job.laser_visual_editor = enabled

    @api.depends('value_ids.text_value', 'value_ids.image_filename')
    def _compute_summary(self):
        for job in self:
            job.personalisation_summary = job._laser_description()

    # ── CRUD ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('laser.job') or _('New')
        jobs = super(LaserJob, self.with_context(laser_defer_output=True)).create(vals_list)
        jobs._sync_values()
        if not self.env.context.get('laser_defer_output'):
            jobs._generate_output_quietly()
        return jobs.with_env(self.env)

    def write(self, vals):
        res = super(LaserJob, self.with_context(laser_defer_output=True)).write(vals)
        if 'template_id' in vals:
            self._sync_values()
        if OUTPUT_FIELDS & set(vals) and not self.env.context.get('laser_defer_output'):
            self._generate_output_quietly()
        return res

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Fill in the template's elements as soon as a template is picked."""
        for job in self:
            if job.value_ids.element_id != job.template_id.element_ids or not job.value_ids:
                job.value_ids = [(5, 0, 0)] + [
                    (0, 0, job._value_defaults(element)) for element in job.template_id.element_ids
                ]

    @api.model
    def _value_defaults(self, element):
        values = {'element_id': element.id}
        if element.element_type == 'text':
            values['text_value'] = element.default_text or False
        return values

    def _sync_values(self):
        """One value per template element: add the missing ones, drop the others."""
        Value = self.env['laser.job.value'].with_context(laser_defer_output=True)
        for job in self:
            elements = job.template_id.element_ids
            job.value_ids.filtered(lambda v: v.element_id not in elements).with_context(
                laser_defer_output=True).unlink()
            missing = elements - job.value_ids.element_id
            if missing:
                Value.create([dict(job._value_defaults(element), job_id=job.id) for element in missing])

    # ── Building the file ────────────────────────────────────────────────
    def _laser_spec(self):
        """Everything the file builders need, as plain data."""
        self.ensure_one()
        template = self.template_id.sudo()
        base = None
        if template.base_file:
            base = {'data': binary_bytes(template, 'base_file'), 'ext': template.base_format}
        elements = []
        values = {value.element_id.id: value for value in self.sudo().value_ids}
        fonts = {}
        for element in template.element_ids:
            value = values.get(element.id)
            item = {
                'type': element.element_type,
                'x': element.x_mm, 'y': element.y_mm, 'w': element.width_mm, 'h': element.height_mm,
                'align': element.text_align, 'auto_fit': element.auto_fit, 'multiline': element.multiline,
                'font_size': element.font_size_mm, 'color': element.color, 'fit': element.image_fit,
                'font_family': element.font_id.css_family or 'sans-serif',
                'name': element.name,
            }
            if element.element_type == 'text':
                text = value.text_value if value else element.default_text
                if element.max_length and text:
                    text = text[:element.max_length]
                item['text'] = text or ''
                if element.font_id:
                    if element.font_id.id not in fonts:
                        fonts[element.font_id.id] = element.font_id._font_data()
                    item['font_data'] = fonts[element.font_id.id]
            else:
                if value and value.image:
                    item['image'] = binary_bytes(value, 'image')
                    item['image_ext'] = extension(value.image_filename)
                elif element.default_image:
                    item['image'] = binary_bytes(element, 'default_image')
                    item['image_ext'] = extension(element.default_image_filename)
            elements.append(item)
        return {
            'operation': template.operation,
            'width': template.width_mm,
            'height': template.height_mm,
            'dpi': template.dpi,
            'grayscale': template.grayscale,
            'base': base,
            'elements': elements,
        }

    def _source_extension(self, spec):
        """Format of the picture uploaded for the job: customer/employee uploads first."""
        for value in self.value_ids.sorted(lambda v: (v.element_id.sequence, v.element_id.id)):
            if value.element_type == 'image' and value.image and value.image_filename:
                return extension(value.image_filename)
        for element in spec['elements']:
            if element.get('image_ext'):
                return element['image_ext']
        return (spec.get('base') or {}).get('ext')

    def _build_output(self):
        """(bytes, extension) of the job's laser file; raises UserError when it can't be made."""
        self.ensure_one()
        spec = self._laser_spec()
        try:
            if spec['operation'] in VECTOR_OPERATIONS:
                return svg_tools.build_svg(spec), 'svg'
            ext = formats.output_extension('engrave', self._source_extension(spec))
            if ext == 'heic' and not raster_tools.HEIF_SUPPORTED:
                return self._heic_passthrough(spec), ext
            return raster_tools.build_raster(spec, ext), ext
        except (svg_tools.SvgError, raster_tools.RasterError) as error:
            raise UserError(str(error)) from error

    @api.model
    def _heic_passthrough(self, spec):
        """Without HEIC support, a job that is just one uploaded HEIC picture keeps it as is."""
        pictures = [el for el in spec['elements'] if el['type'] == 'image' and el.get('image')]
        texts = [el for el in spec['elements'] if el['type'] == 'text' and (el.get('text') or '').strip()]
        if len(pictures) == 1 and not texts and not (spec.get('base') or {}).get('data'):
            return pictures[0]['image']
        raise raster_tools.RasterError(_(
            'HEIC pictures can only be combined with text or other artwork when the pillow-heif '
            'library is installed on the server. Please upload a jpg or png picture instead.'
        ))

    def _output_basename(self):
        return re.sub(r'[^A-Za-z0-9_-]+', '-', self.name or 'laser-job').strip('-') or 'laser-job'

    def _generate_output(self):
        """Make the laser file again; raises UserError when it can't be made."""
        for job in self:
            data, ext = job._build_output()
            job.with_context(laser_defer_output=True).sudo().write({
                'output_file': base64.b64encode(data),
                'output_filename': '%s.%s' % (job._output_basename(), ext),
                'output_format': ext,
                'output_date': fields.Datetime.now(),
                'output_error': False,
            })

    def _generate_output_quietly(self):
        """Make the laser file again, keeping a problem on the job instead of raising."""
        for job in self:
            if not job.template_id:
                continue
            try:
                with self.env.cr.savepoint():
                    job._generate_output()
            except (UserError, ValueError, OSError) as error:
                _logger.info('Laser job %s: no file: %s', job.name, error)
                job.with_context(laser_defer_output=True).sudo().write({
                    'output_file': False,
                    'output_filename': False,
                    'output_format': False,
                    'output_date': False,
                    'output_error': str(error.args[0] if error.args else error),
                })

    def _laser_description(self):
        """The personalisation in words, e.g. for order lines."""
        self.ensure_one()
        lines = []
        for value in self.value_ids.sorted(lambda v: (v.element_id.sequence, v.element_id.id)):
            if value.element_type == 'text':
                if value.text_value:
                    lines.append('%s: %s' % (value.element_id.name, ' / '.join(value.text_value.splitlines())))
            elif value.image_filename:
                lines.append('%s: %s' % (value.element_id.name, value.image_filename))
        return '\n'.join(lines)

    def _check_complete(self):
        for job in self:
            missing = job.value_ids.filtered(
                lambda v: v.element_id.required and not (
                    (v.element_type == 'text' and (v.text_value or '').strip())
                    or (v.element_type == 'image' and (v.image or v.element_id.default_image))
                )
            )
            if missing:
                raise UserError(_(
                    '%(job)s still needs: %(fields)s.',
                    job=job.name, fields=', '.join(missing.element_id.mapped('name')),
                ))

    # ── Actions ──────────────────────────────────────────────────────────
    def action_generate_output(self):
        self._generate_output()
        return True

    def action_confirm(self):
        jobs = self.filtered(lambda j: j.state == 'draft')
        jobs._check_complete()
        jobs._generate_output()
        jobs.write({'state': 'confirmed'})
        return True

    def action_start(self):
        self.filtered(lambda j: j.state in ('draft', 'confirmed')).action_confirm()
        self.filtered(lambda j: j.state == 'confirmed').write({'state': 'in_progress'})
        return True

    def action_done(self):
        todo = self.filtered(lambda j: j.state in ('draft', 'confirmed', 'in_progress'))
        todo.filtered(lambda j: j.state == 'draft').action_confirm()
        todo.write({'state': 'done', 'date_done': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self.filtered(lambda j: j.state != 'done').write({'state': 'cancelled'})
        return True

    def action_draft(self):
        self.filtered(lambda j: j.state in ('confirmed', 'cancelled')).write({'state': 'draft'})
        return True

    def action_download_output(self):
        self.ensure_one()
        if not self.output_file:
            self._generate_output()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/laser.job/%s/output_file/%s?download=true' % (self.id, self.output_filename),
            'target': 'self',
        }


class LaserJobValue(models.Model):
    """What a job puts in one of its template's variable elements."""
    _name = 'laser.job.value'
    _description = 'Laser Job Value'
    _order = 'sequence, id'

    job_id = fields.Many2one('laser.job', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='job_id.company_id', store=True)
    element_id = fields.Many2one('laser.template.element', string='Element', required=True, ondelete='cascade')
    sequence = fields.Integer(related='element_id.sequence', store=True)
    name = fields.Char(related='element_id.name', string='Element Name')
    element_type = fields.Selection(related='element_id.element_type', string='Type')
    required = fields.Boolean(related='element_id.required')
    customer_editable = fields.Boolean(related='element_id.customer_editable')
    help_text = fields.Char(related='element_id.help_text')
    operation = fields.Selection(related='job_id.operation')
    text_value = fields.Text(string='Text')
    image = fields.Binary(string='Picture / Artwork', attachment=True)
    image_filename = fields.Char(string='File Name')

    @api.constrains('text_value')
    def _check_text_value(self):
        for value in self:
            limit = value.element_id.max_length
            if limit and value.text_value and len(value.text_value) > limit:
                raise ValidationError(_(
                    '"%(name)s" can have up to %(limit)s characters.', name=value.element_id.name, limit=limit,
                ))

    @api.constrains('image', 'image_filename')
    def _check_image(self):
        for value in self:
            if not value.image:
                continue
            value.job_id.template_id._check_upload(value.image_filename, value.element_id.name)
            data = binary_bytes(value, 'image')
            if data and len(data) > max_upload_bytes(self.env):
                raise ValidationError(_('"%s" is too large.', value.element_id.name))
            ext = extension(value.image_filename)
            try:
                if ext == 'svg':
                    svg_tools.parse_svg(data)
                elif ext != 'heic' or raster_tools.HEIF_SUPPORTED:
                    raster_tools.open_image(data)
            except (svg_tools.SvgError, raster_tools.RasterError) as error:
                raise ValidationError('%s: %s' % (value.element_id.name, error)) from error

    @api.model_create_multi
    def create(self, vals_list):
        values = super().create(vals_list)
        if not self.env.context.get('laser_defer_output'):
            values.job_id._generate_output_quietly()
        return values

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('laser_defer_output') and {'text_value', 'image', 'image_filename'} & set(vals):
            self.job_id._generate_output_quietly()
        return res

    def _image_url(self):
        self.ensure_one()
        if not self.image:
            return ''
        return '/laser_jobbing/value/%s/image?unique=%s' % (
            self.id, int(self.write_date.timestamp()) if self.write_date else 0,
        )
