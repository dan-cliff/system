# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    embroidery_submission_count = fields.Integer(compute='_compute_embroidery_counts')
    embroidery_job_count = fields.Integer(compute='_compute_embroidery_counts')

    @api.depends('order_line.embroidery_submission_id', 'order_line.embroidery_job_ids')
    def _compute_embroidery_counts(self):
        for order in self:
            order.embroidery_submission_count = len(order.order_line.embroidery_submission_id)
            order.embroidery_job_count = len(order.order_line.embroidery_job_ids)

    def action_view_embroidery_submissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Embroidery Submissions'),
            'res_model': 'embroidery.submission',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.order_line.embroidery_submission_id.ids)],
        }

    def action_view_embroidery_jobs(self):
        self.ensure_one()
        jobs = self.order_line.embroidery_job_ids
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_job')
        action.update({'domain': [('id', 'in', jobs.ids)], 'context': {}})
        if len(jobs) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': jobs.id})
        return action

    def action_confirm(self):
        res = super().action_confirm()
        self._embroidery_create_jobs()
        return res

    def _embroidery_create_jobs(self):
        """One embroidery job for every submitted design on the confirmed orders."""
        for line in self.order_line.filtered(lambda l: l.embroidery_submission_id and not l.embroidery_job_ids):
            submission = line.embroidery_submission_id.sudo()
            if submission.state == 'done':
                submission._create_job(line.product_uom_qty, sale_line=line.sudo())

    # ── Website cart ──────────────────────────────────────────────────────
    # (these methods only exist with website_sale, which this module depends on)

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        product = self.env['product.product'].browse(product_id)
        if product.embroidery_dynamic_pricing and not kwargs.get('embroidery_submission_id'):
            raise UserError(_(
                'The price of "%s" depends on your embroidery file. Upload your .pes file on the '
                'product page to get a price and add it to your cart.', product.display_name,
            ))
        return super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)

    def _cart_find_product_line(self, product_id, uom_id, linked_line_id=False,
                                no_variant_attribute_value_ids=None, **kwargs):
        lines = super()._cart_find_product_line(
            product_id, uom_id, linked_line_id=linked_line_id,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids, **kwargs,
        )
        submission_id = kwargs.get('embroidery_submission_id')
        # Every uploaded file is its own line; the same file adds to its line.
        return lines.filtered(lambda line: line.embroidery_submission_id.id == (submission_id or False))

    def _prepare_order_line_values(self, product_id, quantity, uom_id, **kwargs):
        values = super()._prepare_order_line_values(product_id, quantity, uom_id, **kwargs)
        submission_id = kwargs.get('embroidery_submission_id')
        if submission_id:
            submission = self.env['embroidery.submission'].browse(submission_id)
            product = self.env['product.product'].browse(values['product_id'])
            values['embroidery_submission_id'] = submission.id
            values['name'] = '%s\n%s' % (
                product.with_context(lang=self._get_lang()).display_name,
                submission.with_context(lang=self._get_lang())._sale_line_description(),
            )
        return values


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    embroidery_submission_id = fields.Many2one(
        'embroidery.submission',
        string='Embroidery Submission',
        index='btree_not_null',
        copy=True,
        domain="[('state', '=', 'done'), ('company_id', '=', company_id)]",
        help='The price of this line comes from the estimate of this embroidery file.',
    )
    embroidery_job_ids = fields.One2many('embroidery.job', 'sale_line_id', string='Embroidery Jobs')
    embroidery_dynamic_pricing = fields.Boolean(related='product_id.embroidery_dynamic_pricing')
    embroidery_stitch_count = fields.Integer(related='embroidery_submission_id.stitch_count', string='Stitches')
    embroidery_duration = fields.Char(related='embroidery_submission_id.duration_display', string='Est. Duration')

    @api.depends('embroidery_submission_id', 'embroidery_submission_id.price')
    def _compute_price_unit(self):
        return super()._compute_price_unit()

    def _get_display_price(self):
        self.ensure_one()
        submission = self.embroidery_submission_id
        if not submission:
            return super()._get_display_price()
        order = self.order_id
        return submission.currency_id._convert(
            submission.price,
            self.currency_id or order.currency_id or submission.currency_id,
            self.company_id or submission.company_id,
            order.date_order or fields.Date.context_today(self),
        )

    @api.onchange('embroidery_submission_id')
    def _onchange_embroidery_submission_id(self):
        for line in self:
            submission = line.embroidery_submission_id
            if not submission:
                continue
            if not line.product_id and submission.product_id:
                line.product_id = submission.product_id
            line.name = '%s\n%s' % (line.product_id.display_name or '', submission._sale_line_description())

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        if self.embroidery_submission_id:
            values['embroidery_submission_id'] = self.embroidery_submission_id.id
        return values
