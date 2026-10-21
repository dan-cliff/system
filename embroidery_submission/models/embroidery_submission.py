# -*- coding: utf-8 -*-
import base64
import logging
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.embroidery_jobbing.lib import pes
from odoo.addons.embroidery_jobbing.models.embroidery_stitchout import format_duration

_logger = logging.getLogger(__name__)

STITCHES_PER_MINUTE_PARAM = 'embroidery_submission.stitches_per_minute'
DEFAULT_STITCHES_PER_MINUTE = 600

# Fields whose change means the price has to be worked out again.
PRICING_FIELDS = {'profile_id'}


class EmbroiderySubmission(models.Model):
    """An embroidery file submitted for a price: what it needs and what it costs."""
    _name = 'embroidery.submission'
    _description = 'Embroidery Submission'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    product_id = fields.Many2one(
        'product.product', string='Product', tracking=True,
        domain=[('embroidery_dynamic_pricing', '=', True)],
        help='The embroidery product this submission is priced for.',
    )
    profile_id = fields.Many2one(
        'embroidery.pricing.profile', string='Pricing Profile', required=True, tracking=True,
        default=lambda self: self._default_profile(),
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    source = fields.Selection(
        [('backend', 'Backend'), ('website', 'Website')],
        default='backend', required=True, readonly=True,
    )
    access_token = fields.Char(copy=False, readonly=True, default=lambda self: uuid.uuid4().hex)
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Estimated'), ('error', 'Error')],
        string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True,
    )

    # ── File ──────────────────────────────────────────────────────────────
    file = fields.Binary(string='Design File (.pes)', attachment=True, copy=False)
    filename = fields.Char(string='File Name', tracking=True)
    error_message = fields.Text(string='Error', readonly=True)
    warnings = fields.Text(string='Notes', readonly=True)

    # ── Read from the file ────────────────────────────────────────────────
    stitch_count = fields.Integer(string='Stitches', readonly=True)
    color_count = fields.Integer(string='Colours', readonly=True)
    color_change_count = fields.Integer(string='Colour Changes', readonly=True)
    trim_count = fields.Integer(string='Trims', readonly=True)
    jump_count = fields.Integer(string='Jumps', readonly=True)
    width_mm = fields.Float(string='Width (mm)', digits=(16, 1), readonly=True)
    height_mm = fields.Float(string='Height (mm)', digits=(16, 1), readonly=True)
    size_display = fields.Char(string='Size', compute='_compute_size_display')
    color_ids = fields.One2many('embroidery.submission.color', 'submission_id', string='Thread Colours',
                                readonly=True)

    # ── Estimated time ────────────────────────────────────────────────────
    stitches_per_minute = fields.Integer(
        string='Stitches per Minute', readonly=True,
        help='The "Estimate duration based on stitches" setting used for this estimate.',
    )
    stitch_seconds = fields.Integer(string='Stitching Time (s)', readonly=True)
    color_change_seconds = fields.Integer(string='Colour Change Time (s)', readonly=True)
    hooping_seconds = fields.Integer(string='Hooping Time (s)', readonly=True)
    duration_seconds = fields.Integer(string='Estimated Duration (s)', readonly=True)
    duration_hours = fields.Float(string='Estimated Hours', compute='_compute_duration', store=True,
                                  digits=(16, 2))
    duration_display = fields.Char(string='Estimated Duration', compute='_compute_duration', store=True)
    stitch_time_display = fields.Char(string='Stitching Time', compute='_compute_time_displays')
    color_change_time_display = fields.Char(string='Colour Change Time', compute='_compute_time_displays')
    hooping_time_display = fields.Char(string='Hooping Time', compute='_compute_time_displays')

    # ── Costing (per piece) ───────────────────────────────────────────────
    stitch_cost = fields.Monetary(string='Stitch Cost', readonly=True)
    color_change_cost = fields.Monetary(string='Colour Change Fees', readonly=True)
    machine_cost = fields.Monetary(string='Machine Time Cost', readonly=True)
    setup_cost = fields.Monetary(string='Setup Fee', readonly=True)
    cost_total = fields.Monetary(string='Total Cost', readonly=True, tracking=True)
    markup_amount = fields.Monetary(string='Markup', readonly=True)
    price = fields.Monetary(string='Price per Piece', readonly=True, tracking=True,
                            help='Sales price (excluding taxes) to embroider this design once.')

    # ── Sales / invoicing / production ────────────────────────────────────
    sale_line_ids = fields.One2many('sale.order.line', 'embroidery_submission_id', string='Sales Order Lines')
    invoice_line_ids = fields.One2many('account.move.line', 'embroidery_submission_id', string='Invoice Lines')
    job_ids = fields.One2many('embroidery.job', 'submission_id', string='Jobs')
    design_id = fields.Many2one('embroidery.design', string='Design', readonly=True, copy=False,
                                help='The design created from this file for the jobs.')
    sale_order_count = fields.Integer(compute='_compute_sale_invoice_counts')
    invoice_count = fields.Integer(compute='_compute_sale_invoice_counts')
    job_count = fields.Integer(compute='_compute_sale_invoice_counts')
    locked = fields.Boolean(
        compute='_compute_sale_invoice_counts',
        help='Invoiced submissions keep their figures so the invoice stays as recorded.',
    )

    @api.model
    def _default_profile(self, company=None, product=None):
        company = company or self.env.company
        if product and product.embroidery_profile_id:
            return product.embroidery_profile_id
        return company.embroidery_profile_id or self.env['embroidery.pricing.profile'].search(
            ['|', ('company_id', '=', False), ('company_id', '=', company.id)], limit=1,
        )

    @api.model
    def _stitches_per_minute(self):
        """Settings › Embroidery › Submission Defaults › Estimate duration based on stitches."""
        value = self.env['ir.config_parameter'].sudo().get_param(STITCHES_PER_MINUTE_PARAM)
        try:
            value = int(value or DEFAULT_STITCHES_PER_MINUTE)
        except ValueError:
            value = DEFAULT_STITCHES_PER_MINUTE
        return value if value > 0 else DEFAULT_STITCHES_PER_MINUTE

    @api.depends('width_mm', 'height_mm', 'stitch_count')
    def _compute_size_display(self):
        for submission in self:
            submission.size_display = (
                '%.1f x %.1f mm' % (submission.width_mm, submission.height_mm) if submission.stitch_count else ''
            )

    @api.depends('duration_seconds')
    def _compute_duration(self):
        for submission in self:
            submission.duration_hours = submission.duration_seconds / 3600.0
            submission.duration_display = (
                format_duration(submission.duration_seconds) if submission.duration_seconds else ''
            )

    @api.depends('stitch_seconds', 'color_change_seconds', 'hooping_seconds')
    def _compute_time_displays(self):
        for submission in self:
            submission.stitch_time_display = format_duration(submission.stitch_seconds)
            submission.color_change_time_display = format_duration(submission.color_change_seconds)
            submission.hooping_time_display = format_duration(submission.hooping_seconds)

    @api.depends('sale_line_ids', 'invoice_line_ids.parent_state', 'job_ids')
    def _compute_sale_invoice_counts(self):
        for submission in self:
            submission.sale_order_count = len(submission.sale_line_ids.order_id)
            moves = submission.invoice_line_ids.move_id
            submission.invoice_count = len(moves)
            submission.job_count = len(submission.job_ids)
            submission.locked = bool(moves.filtered(lambda m: m.state != 'cancel'))

    # ─────────────────────────────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('embroidery.submission') or _('New')
            if not vals.get('profile_id'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                product = self.env['product.product'].browse(vals.get('product_id'))
                vals['profile_id'] = self._default_profile(company, product).id
        submissions = super().create(vals_list)
        submissions.filtered('file')._analyse()
        return submissions

    def write(self, vals):
        if self.filtered('locked') and (PRICING_FIELDS | {'file'}) & set(vals):
            raise UserError(_(
                'This submission has been invoiced, so its file and costing can no longer change. '
                'Duplicate it to price a new version.'
            ))
        res = super().write(vals)
        if vals.get('file'):
            self._analyse()
        elif 'file' in vals:
            self._reset_results()
        elif PRICING_FIELDS & set(vals) and not self.env.context.get('embroidery_no_reprice'):
            self._update_pricing()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for submission, vals in zip(self, vals_list):
            # The file is not copied by the ORM (copy=False): copy it so the
            # duplicate is read and priced on its own.
            vals.setdefault('file', submission.file)
        return vals_list

    # ─────────────────────────────────────────────────────────────────────
    # Reading the file
    # ─────────────────────────────────────────────────────────────────────

    def _reset_results(self):
        self.with_context(embroidery_no_reprice=True).write({
            'state': 'draft',
            'color_ids': [fields.Command.clear()],
            'image_1920': False,
            'stitch_count': 0,
            'color_count': 0,
            'color_change_count': 0,
            'trim_count': 0,
            'jump_count': 0,
            'width_mm': 0.0,
            'height_mm': 0.0,
            'error_message': False,
            'warnings': False,
            'stitches_per_minute': 0,
            'stitch_seconds': 0,
            'color_change_seconds': 0,
            'hooping_seconds': 0,
            'duration_seconds': 0,
            'stitch_cost': 0.0,
            'color_change_cost': 0.0,
            'machine_cost': 0.0,
            'setup_cost': 0.0,
            'cost_total': 0.0,
            'markup_amount': 0.0,
            'price': 0.0,
        })

    def _analyse(self):
        """Read the .pes file: stitches, colours, size and preview, then price it."""
        for submission in self:
            if not submission.file:
                submission._reset_results()
                continue
            if submission.filename and not submission.filename.lower().endswith('.pes'):
                submission._set_error(_('"%s" is not a .pes file. Save the design as Brother .pes and upload that.',
                                        submission.filename))
                continue
            try:
                design = pes.read_pes(base64.b64decode(submission.with_context(bin_size=False).file))
            except pes.PesError as error:
                submission._set_error(str(error))
                continue
            except Exception as error:  # noqa: BLE001 - a broken upload must not crash the form
                _logger.exception('Could not read embroidery submission %s', submission.filename)
                submission._set_error(_('The file could not be read: %s', error))
                continue
            if not design.stitch_count:
                submission._set_error(_('The file has no stitches.'))
                continue
            submission._apply_design(design)
        self._update_pricing()

    def _set_error(self, message):
        self.ensure_one()
        self._reset_results()
        self.with_context(embroidery_no_reprice=True).write({'state': 'error', 'error_message': message})

    def _apply_design(self, design):
        self.ensure_one()
        values = {
            'state': 'done',
            'stitch_count': design.stitch_count,
            'color_count': len(design.colors),
            'color_change_count': design.color_change_count,
            'trim_count': design.trim_count,
            'jump_count': design.jump_count,
            'width_mm': design.width_mm,
            'height_mm': design.height_mm,
            'error_message': False,
            'warnings': self._fit_warning(design.width_mm, design.height_mm) or False,
            'color_ids': [fields.Command.clear()] + [
                fields.Command.create({
                    'sequence': number,
                    'palette_index': color['index'],
                    'name': color['name'],
                    'color_hex': color['hex'],
                    'stitch_count': color['stitches'],
                })
                for number, color in enumerate(design.colors, start=1)
            ],
        }
        try:
            values['image_1920'] = base64.b64encode(design.preview_png())
        except Exception:  # the figures are still useful without a preview
            _logger.exception('Could not draw the preview of embroidery submission %s', self.id)
        self.with_context(embroidery_no_reprice=True).write(values)

    @api.model
    def _fit_warning(self, width, height):
        """A note when the design is bigger than every hoop we have."""
        hoops = self.env['embroidery.hoop'].sudo().search([('width_mm', '>', 0), ('height_mm', '>', 0)])
        if not hoops or not (width or height):
            return ''
        fits = hoops.filtered(lambda hoop: (width <= hoop.width_mm and height <= hoop.height_mm)
                              or (width <= hoop.height_mm and height <= hoop.width_mm))
        if fits:
            return ''
        largest = max(hoops, key=lambda hoop: hoop.width_mm * hoop.height_mm)
        return _('The design (%(width).0f x %(height).0f mm) is larger than our largest hoop '
                 '(%(hoop)s, %(hoop_width).0f x %(hoop_height).0f mm). We will be in touch about it.',
                 width=width, height=height, hoop=largest.name,
                 hoop_width=largest.width_mm, hoop_height=largest.height_mm)

    def action_analyse(self):
        if self.filtered('locked'):
            raise UserError(_('Invoiced submissions cannot be read again. Duplicate it instead.'))
        if not self.filtered('file'):
            raise UserError(_('Attach a .pes file first.'))
        self._analyse()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Time and price
    # ─────────────────────────────────────────────────────────────────────

    def _update_pricing(self):
        spm = self._stitches_per_minute()
        for submission in self:
            if submission.state != 'done' or not submission.profile_id or submission.locked:
                continue
            profile = submission.profile_id
            currency = submission.currency_id
            company = submission.company_id
            date = fields.Date.context_today(submission)

            def convert(amount):
                return profile.currency_id._convert(amount, currency, company, date)

            stitch_seconds = round(submission.stitch_count / spm * 60.0)
            change_seconds = submission.color_change_count * max(profile.color_change_seconds, 0)
            hooping_seconds = round(max(profile.hooping_minutes, 0.0) * 60.0)
            duration = stitch_seconds + change_seconds + hooping_seconds

            stitch_cost = submission.stitch_count / 1000.0 * convert(profile.price_per_thousand_stitches)
            change_cost = submission.color_change_count * convert(profile.color_change_fee)
            machine_cost = duration / 3600.0 * convert(profile.machine_rate_per_hour)
            setup_cost = convert(profile.setup_fee)
            cost_total = stitch_cost + change_cost + machine_cost + setup_cost
            price = max(cost_total * (1 + profile.markup_percent / 100.0), convert(profile.minimum_price))
            submission.with_context(embroidery_no_reprice=True).write({
                'stitches_per_minute': spm,
                'stitch_seconds': stitch_seconds,
                'color_change_seconds': change_seconds,
                'hooping_seconds': hooping_seconds,
                'duration_seconds': duration,
                'stitch_cost': currency.round(stitch_cost),
                'color_change_cost': currency.round(change_cost),
                'machine_cost': currency.round(machine_cost),
                'setup_cost': currency.round(setup_cost),
                'cost_total': currency.round(cost_total),
                'markup_amount': currency.round(price - cost_total),
                'price': currency.round(price),
            })

    def action_update_pricing(self):
        if self.filtered('locked'):
            raise UserError(_('Invoiced submissions keep their recorded costing.'))
        self._update_pricing()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Sales
    # ─────────────────────────────────────────────────────────────────────

    def _sale_line_description(self):
        """Text recorded on the sales order / invoice line."""
        self.ensure_one()
        parts = [_('Embroidery: %s', self.filename or self.name)]
        parts.append(_('%(stitches)s stitches, %(colours)s colour(s), %(changes)s colour change(s)',
                       stitches='{:,}'.format(self.stitch_count), colours=self.color_count,
                       changes=self.color_change_count))
        summary = []
        if self.size_display:
            summary.append(self.size_display)
        if self.duration_display:
            summary.append(_('Est. %s per piece', self.duration_display))
        if summary:
            parts.append(' · '.join(summary))
        parts.append(_('Submission %s', self.name))
        return '\n'.join(parts)

    def action_create_quotation(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('The file has to be estimated before it can be quoted.'))
        product = self.product_id or self.env['product.product'].search(
            [('embroidery_dynamic_pricing', '=', True), ('sale_ok', '=', True)], limit=1,
        )
        if not product:
            raise UserError(_('Choose a product with "Embroidery Dynamic Pricing" enabled on the submission first.'))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id or self.env.user.partner_id.id,
            'company_id': self.company_id.id,
            'order_line': [fields.Command.create({
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'embroidery_submission_id': self.id,
                'name': '%s\n%s' % (product.display_name, self._sale_line_description()),
            })],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
        }

    def action_view_sale_orders(self):
        self.ensure_one()
        orders = self.sale_line_ids.order_id
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action.update({'domain': [('id', 'in', orders.ids)], 'context': {}})
        if len(orders) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': orders.id})
        return action

    def action_view_invoices(self):
        self.ensure_one()
        moves = self.invoice_line_ids.move_id
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action.update({'domain': [('id', 'in', moves.ids)], 'context': {}})
        if len(moves) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': moves.id})
        return action

    # ─────────────────────────────────────────────────────────────────────
    # Production
    # ─────────────────────────────────────────────────────────────────────

    def _get_or_create_design(self):
        """The Embroidery design for this file, created the first time it is needed."""
        self.ensure_one()
        if not self.design_id:
            self.design_id = self.env['embroidery.design'].create({
                'name': (self.filename or self.name).rsplit('.', 1)[0],
                'design_file': self.with_context(bin_size=False).file,
                'design_filename': self.filename or '%s.pes' % self.name,
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
            })
        return self.design_id

    def _create_job(self, quantity=1, sale_line=None):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('%s has no readable design, so no job can be made from it.', self.name))
        order = sale_line.order_id if sale_line else self.env['sale.order']
        title = self.filename or self.name
        if order:
            title = _('%(order)s - %(file)s', order=order.name, file=title)
        return self.env['embroidery.job'].create({
            'title': title,
            'company_id': self.company_id.id,
            'partner_id': (order.partner_id or self.partner_id).id,
            'product_qty': max(int(quantity or 1), 1),
            'design_id': self._get_or_create_design().id,
            'date_deadline': order.commitment_date and order.commitment_date.date(),
            'submission_id': self.id,
            'sale_line_id': sale_line.id if sale_line else False,
        })

    def action_create_job(self):
        self.ensure_one()
        quantity = sum(self.sale_line_ids.filtered(lambda l: l.state == 'sale').mapped('product_uom_qty')) or 1
        job = self._create_job(quantity)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'embroidery.job',
            'res_id': job.id,
            'view_mode': 'form',
        }

    def action_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_job')
        action.update({'domain': [('id', 'in', self.job_ids.ids)], 'context': {}})
        if len(self.job_ids) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': self.job_ids.id})
        return action

    @api.model
    def _gc_website_submissions(self):
        """Remove website uploads that never made it into a cart."""
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        self.sudo().search([
            ('source', '=', 'website'),
            ('sale_line_ids', '=', False),
            ('create_date', '<', limit),
        ]).unlink()


class EmbroiderySubmissionColor(models.Model):
    _name = 'embroidery.submission.color'
    _description = 'Embroidery Submission Thread Colour'
    _order = 'submission_id, sequence, id'

    submission_id = fields.Many2one('embroidery.submission', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='submission_id.company_id', store=True)
    sequence = fields.Integer(string='#')
    palette_index = fields.Integer(string='Brother Colour No.')
    name = fields.Char(string='Thread')
    color_hex = fields.Char(string='Colour')
    stitch_count = fields.Integer(string='Stitches')
