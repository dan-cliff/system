from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_is_zero, format_datetime


class KennelBooking(models.Model):
    """Invoicing: the Products tab, invoices and amendment invoices, and the payment status."""
    _inherit = 'kennel.booking'

    invoicing_enabled = fields.Boolean(related='company_id.kennel_invoicing')
    product_line_ids = fields.One2many('kennel.booking.product', 'booking_id', string='Products', copy=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount_products = fields.Monetary(string='Products Total', compute='_compute_amount_products',
                                      help='Before tax.')
    invoice_ids = fields.One2many('account.move', 'kennel_booking_id', string='Invoices',
                                  groups='account.group_account_invoice')
    invoice_count = fields.Integer(compute='_compute_invoice_status', compute_sudo=True, store=True)
    amount_invoiced = fields.Monetary(compute='_compute_invoice_status', compute_sudo=True, store=True,
                                      help='Posted invoices less credit notes, tax included.')
    amount_due = fields.Monetary(compute='_compute_invoice_status', compute_sudo=True, store=True)
    payment_status = fields.Selection(
        [
            ('not_invoiced', 'Not Invoiced'),
            ('draft', 'Invoice Draft'),
            ('not_paid', 'Not Paid'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
        ],
        compute='_compute_invoice_status', compute_sudo=True, store=True, default='not_invoiced',
        help='From the booking\'s invoices in Accounting.',
    )
    invoice_summary = fields.Html(compute='_compute_invoice_summary', sanitize=False)
    # Invoicing workflow (hidden): products not invoiced yet, and the changes the user chose not to invoice.
    has_products_to_invoice = fields.Boolean(compute='_compute_amendment')
    show_amendment_prompt = fields.Boolean(compute='_compute_amendment')
    amendment_declined = fields.Char(copy=False, help='The uninvoiced changes when No was last chosen.')

    @api.depends('product_line_ids.price_subtotal')
    def _compute_amount_products(self):
        for booking in self:
            booking.amount_products = sum(booking.product_line_ids.mapped('price_subtotal'))

    @api.depends('invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.amount_total_signed',
                 'invoice_ids.amount_residual_signed')
    def _compute_invoice_status(self):
        for booking in self:
            invoices = booking.invoice_ids.filtered(lambda move: move.state != 'cancel')
            posted = invoices.filtered(lambda move: move.state == 'posted')
            booking.invoice_count = len(invoices)
            booking.amount_invoiced = sum(posted.mapped('amount_total_signed'))
            booking.amount_due = sum(posted.mapped('amount_residual_signed'))
            invoices_only = posted.filtered(lambda move: move.move_type == 'out_invoice')
            if not invoices:
                booking.payment_status = 'not_invoiced'
            elif not posted:
                booking.payment_status = 'draft'
            elif float_is_zero(booking.amount_due, precision_rounding=booking.currency_id.rounding or 0.01):
                booking.payment_status = 'paid'
            elif any(move.payment_state in ('partial', 'in_payment', 'paid') for move in invoices_only):
                booking.payment_status = 'partial'
            else:
                booking.payment_status = 'not_paid'

    @api.depends('invoice_count', 'amount_due')
    def _compute_invoice_summary(self):
        """The booking's invoices as a small table, readable by keepers without Accounting access."""
        for booking in self:
            invoices = booking.sudo().invoice_ids.sorted('id')
            if not invoices:
                booking.invoice_summary = False
                continue
            rows = Markup('').join(
                Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td class="text-end">%s</td>'
                       '<td class="text-end">%s</td><td>%s</td></tr>') % (
                    move.name if move.name and move.name != '/' else self.env._('Draft'),
                    dict(move._fields['move_type']._description_selection(self.env)).get(move.move_type),
                    move.invoice_date.strftime('%d/%m/%Y') if move.invoice_date else '',
                    move.currency_id.format(move.amount_total_signed),
                    move.currency_id.format(move.amount_residual_signed) if move.state == 'posted' else '',
                    dict(move._fields['state']._description_selection(self.env)).get(move.state)
                    if move.state != 'posted' else
                    dict(move._fields['payment_state']._description_selection(self.env)).get(move.payment_state),
                )
                for move in invoices
            )
            booking.invoice_summary = Markup(
                '<table class="table table-sm mb-0"><thead><tr><th>%s</th><th>%s</th><th>%s</th>'
                '<th class="text-end">%s</th><th class="text-end">%s</th><th>%s</th></tr></thead><tbody>%s</tbody></table>'
            ) % (self.env._('Number'), self.env._('Type'), self.env._('Date'), self.env._('Total'),
                 self.env._('Due'), self.env._('Status'), rows)

    def _pending_product_lines(self):
        """Product lines (removed ones included) whose quantity differs from what's been invoiced."""
        self.ensure_one()
        lines = self.with_context(active_test=False).product_line_ids
        return lines.filtered(lambda line: not float_is_zero(
            line.qty_to_invoice, precision_rounding=line.product_id.uom_id.rounding or 0.01))

    def _pending_signature(self):
        return ';'.join(f'{line.id}:{line.qty_to_invoice:g}' for line in self._pending_product_lines())

    @api.depends('product_line_ids.qty_to_invoice', 'invoice_count', 'amendment_declined', 'invoicing_enabled')
    def _compute_amendment(self):
        for booking in self:
            pending = booking.invoicing_enabled and bool(booking._pending_product_lines())
            booking.has_products_to_invoice = pending and not booking.invoice_count
            booking.show_amendment_prompt = (
                pending and bool(booking.invoice_count)
                and booking._pending_signature() != (booking.amendment_declined or ''))

    # ------------------------------------------------------------------
    # Raising invoices
    # ------------------------------------------------------------------

    def _booking_details_note(self, amendment=False):
        self.ensure_one()
        when = lambda value: format_datetime(self.env, value, dt_format='dd/MM/yyyy HH:mm')
        header = (self.env._('Amendment to booking %s: changes to products since the last invoice.', self.name)
                  if amendment else self.env._('Booking %s', self.name))
        return '\n'.join([
            header,
            self.env._('Animals: %s', ', '.join(self.resident_ids.mapped('name'))),
            self.env._('Arrival: %(arrival)s - Departure: %(departure)s (%(nights)s nights)',
                       arrival=when(self.arrival_datetime), departure=when(self.departure_datetime),
                       nights=self.nights),
        ])

    def _create_invoice(self, amendment=False):
        """Invoice every product quantity not invoiced yet: additions as positive lines, removals as
        negative ones. When the changes come to less than zero overall, a credit note is raised instead."""
        self.ensure_one()
        if not self.invoicing_enabled:
            raise UserError(self.env._('Turn on "Integrate Bookings with Invoicing" in the Boarding Kennel settings first.'))
        lines = self._pending_product_lines()
        if not lines:
            raise UserError(self.env._('%s: there are no products to invoice.', self.name))
        total = sum(line.qty_to_invoice * line.price_unit for line in lines)
        refund = total < 0
        sign = -1 if refund else 1
        move_vals = {
            'move_type': 'out_refund' if refund else 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'kennel_booking_id': self.id,
            'invoice_user_id': self.env.user.id,
            'invoice_line_ids': [Command.create({
                'display_type': 'line_note',
                'name': self._booking_details_note(amendment=amendment),
            })] + [Command.create({
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.qty_to_invoice * sign,
                'price_unit': line.price_unit,
                'kennel_booking_product_id': line.id,
            }) for line in lines],
        }
        # sudo: keepers raise invoices without having Accounting access themselves.
        invoice = self.env['account.move'].sudo().with_company(self.company_id).create(move_vals)
        self.amendment_declined = False
        label = (self.env._('Credit note') if refund else
                 self.env._('Amendment invoice') if amendment else self.env._('Invoice'))
        self.message_post(body=Markup('%s <a href="#" data-oe-model="account.move" data-oe-id="%s">%s</a>') % (
            self.env._('%(document)s raised as a draft for %(amount)s:', document=label,
                       amount=invoice.currency_id.format(invoice.amount_total)),
            invoice.id, self.env._('view')))
        return invoice

    def _invoice_action(self, invoice):
        if self.env.user.has_group('account.group_account_invoice'):
            action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
            action.update({'res_id': invoice.id, 'views': [(False, 'form')], 'view_mode': 'form', 'domain': []})
            return action
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'sticky': False,
            'message': self.env._('%s raised. Accounting will review and send it.', invoice.display_name),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
        }}

    def action_create_invoice(self):
        self.ensure_one()
        return self._invoice_action(self._create_invoice())

    def action_create_amendment_invoice(self):
        """Yes: invoice the product changes since the last invoice."""
        self.ensure_one()
        return self._invoice_action(self._create_invoice(amendment=True))

    def action_decline_amendment(self):
        """No: don't invoice now; the changes stay pending and are asked about again after the next change."""
        for booking in self:
            booking.amendment_declined = booking._pending_signature()

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action.update({'domain': [('kennel_booking_id', '=', self.id)], 'context': {'create': False}})
        return action
