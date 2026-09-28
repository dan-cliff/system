from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    kennel_booking_id = fields.Many2one('kennel.booking', string='Kennel Booking', index='btree_not_null',
                                        readonly=True, copy=False)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Links an invoice line to the booking product it bills, to work out what's been invoiced.
    kennel_booking_product_id = fields.Many2one('kennel.booking.product', index='btree_not_null',
                                                readonly=True, copy=False)
