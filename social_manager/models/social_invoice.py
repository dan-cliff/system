from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

PARAM_INTEGRATE_ACCOUNTS = 'social_manager.integrate_accounts'
PARAM_INVOICE_PRODUCT = 'social_manager.invoice_product_id'


class SocialInvoice(models.Model):
    """Links a customer invoice to the monetised content it bills: one Platform and a date range,
    with a line per Page / Channel. The invoice itself is not modified beyond the text of its lines."""
    _name = 'social.invoice'
    _inherit = ['mail.thread']
    _description = 'Social Monetisation Invoice'
    _order = 'date_to desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    platform_id = fields.Many2one('social.platform', string='Platform', required=True, readonly=True)
    date_from = fields.Date(string='From', required=True, readonly=True)
    date_to = fields.Date(string='To', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    move_id = fields.Many2one('account.move', string='Invoice', readonly=True, ondelete='set null', copy=False)
    move_state = fields.Selection(related='move_id.state', string='Invoice Status')
    payment_state = fields.Selection(related='move_id.payment_state', string='Payment Status')
    line_ids = fields.One2many('social.invoice.line', 'invoice_id', string='Pages / Channels', readonly=True)
    amount_total = fields.Monetary(string='Total', compute='_compute_amount_total', store=True)

    @api.depends('line_ids.amount')
    def _compute_amount_total(self):
        for invoice in self:
            invoice.amount_total = sum(invoice.line_ids.mapped('amount'))

    @api.depends('name', 'platform_id', 'date_from', 'date_to')
    def _compute_display_name(self):
        for invoice in self:
            if invoice.date_from and invoice.date_to:
                invoice.display_name = '%s - %s (%s to %s)' % (
                    invoice.name, invoice.platform_id.name,
                    invoice.date_from.strftime('%d/%m/%Y'), invoice.date_to.strftime('%d/%m/%Y'))
            else:
                invoice.display_name = invoice.name

    def unlink(self):
        if self.filtered(lambda i: i.move_id and i.move_id.state != 'cancel'):
            raise UserError('Cancel or delete the invoice first.')
        return super().unlink()

    def action_view_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }

    def action_view_income(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_income')
        action['domain'] = [('invoice_line_id.invoice_id', '=', self.id)]
        return action

    # ------------------------------------------------------------------
    @api.model
    def _create_invoices(self, date_from, date_to, platforms=None, company=None):
        """One invoice per Platform for its uninvoiced income in the date range, with a line per
        Page / Channel. Returns the social.invoice records created."""
        company = company or self.env.company
        if platforms is None:
            platforms = self.env['social.platform'].search([('is_monetised', '=', True)])
        Income = self.env['social.income']
        created = self.browse()
        for platform in platforms:
            incomes = Income.search([
                ('platform_id', '=', platform.id),
                ('company_id', '=', company.id),
                ('invoice_line_id', '=', False),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ])
            if not incomes:
                continue
            if not platform.partner_id:
                raise UserError('Set the Paying Partner of %s before invoicing its income.' % platform.name)
            created |= self._create_platform_invoice(platform, incomes, date_from, date_to, company)
        return created

    @api.model
    def _create_platform_invoice(self, platform, incomes, date_from, date_to, company):
        sequence = self.env['ir.sequence'].with_company(company)
        social_invoice = self.create({
            'name': sequence.next_by_code('social.invoice') or 'New',
            'platform_id': platform.id,
            'date_from': date_from,
            'date_to': date_to,
            'company_id': company.id,
        })
        product = self._invoice_product()
        period = '%s to %s' % (date_from.strftime('%d/%m/%Y'), date_to.strftime('%d/%m/%Y'))
        move_lines = []
        channel_lines = []
        for channel in incomes.channel_id.sorted('name'):
            channel_incomes = incomes.filtered(lambda i: i.channel_id == channel)
            amount = sum(channel_incomes.mapped('amount'))
            line = self.env['social.invoice.line'].create({
                'invoice_id': social_invoice.id,
                'channel_id': channel.id,
                'amount': amount,
            })
            channel_incomes.write({'invoice_line_id': line.id})
            channel_lines.append(line)
            description = (
                'Monetised content - Platform: %s - Page / Channel: %s - Period: %s - '
                'Social Manager reference: %s'
            ) % (platform.name, channel.name, period, social_invoice.name)
            line_vals = {'name': description, 'quantity': 1, 'price_unit': amount}
            if product:
                line_vals['product_id'] = product.id
                # Keep our description rather than the product's.
                line_vals['name'] = description
            move_lines.append((0, 0, line_vals))
        move = self.env['account.move'].with_company(company).create({
            'move_type': 'out_invoice',
            'partner_id': platform.partner_id.id,
            'company_id': company.id,
            'invoice_date': date_to,
            'invoice_origin': social_invoice.name,
            'ref': '%s monetised content %s' % (platform.name, period),
            'invoice_line_ids': move_lines,
        })
        social_invoice.move_id = move
        for line, move_line in zip(channel_lines, move.invoice_line_ids.sorted('sequence')):
            line.move_line_id = move_line
        social_invoice.message_post(body='Invoice %s created.' % (move.name or move.display_name))
        return social_invoice

    @api.model
    def _invoice_product(self):
        product_id = self.env['ir.config_parameter'].sudo().get_param(PARAM_INVOICE_PRODUCT)
        product = self.env['product.product'].browse(int(product_id)).exists() if product_id else None
        return product or None

    @api.model
    def _cron_create_invoices(self):
        """Monthly: invoice last month's monetised income (when Integrate to Accounts is on)."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(PARAM_INTEGRATE_ACCOUNTS) not in ('True', 'true', '1'):
            return
        today = fields.Date.context_today(self)
        date_to = today.replace(day=1) - timedelta(days=1)
        date_from = date_to.replace(day=1)
        for company in self.env['res.company'].search([]):
            platforms = self.env['social.platform'].search([
                ('is_monetised', '=', True), ('partner_id', '!=', False), ('company_id', '=', company.id)])
            self.with_company(company)._create_invoices(date_from, date_to, platforms, company)


class SocialInvoiceLine(models.Model):
    _name = 'social.invoice.line'
    _description = 'Social Monetisation Invoice Line'
    _order = 'invoice_id, id'

    invoice_id = fields.Many2one('social.invoice', string='Monetisation Invoice', required=True,
                                 ondelete='cascade', index=True)
    channel_id = fields.Many2one('social.channel', string='Page / Channel', required=True)
    platform_id = fields.Many2one(related='invoice_id.platform_id', store=True)
    date_from = fields.Date(related='invoice_id.date_from')
    date_to = fields.Date(related='invoice_id.date_to')
    company_id = fields.Many2one(related='invoice_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary()
    move_line_id = fields.Many2one('account.move.line', string='Invoice Line', ondelete='set null')
    income_ids = fields.One2many('social.income', 'invoice_line_id', string='Income')
