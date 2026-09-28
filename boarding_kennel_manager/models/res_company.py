import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .kennel_options import parse_times


class ResCompany(models.Model):
    _inherit = 'res.company'

    kennel_observation_times = fields.Char(
        string='Observation Rounds', default='09:00, 16:00',
        help='24-hour times separated by commas. Each one puts an observation for every checked-in '
             'animal on the daily to-do list.',
    )

    kennel_invoicing = fields.Boolean(
        string='Integrate Bookings with Invoicing',
        help='When enabled, bookings will have the ability to raise an invoice in the Accounting app and '
             'reflect the payment status in the booking.',
    )
    kennel_warehouse_ids = fields.Many2many(
        'stock.warehouse', 'kennel_warehouse_company_rel', 'company_id', 'warehouse_id', string='Warehouse/s',
    )
    kennel_product_categ_ids = fields.Many2many(
        'product.category', 'kennel_product_categ_company_rel', 'company_id', 'categ_id',
        string='Product Categories',
        help='Only products in these categories (or their sub-categories) can be added to bookings.',
    )

    def _kennel_product_domain(self):
        """Products offered on bookings: saleable ones in the kennel's product categories (all saleable
        products while no category is set)."""
        self.ensure_one()
        domain = [('sale_ok', '=', True), ('company_id', 'in', [False, self.id])]
        if self.kennel_product_categ_ids:
            domain.append(('categ_id', 'child_of', self.kennel_product_categ_ids.ids))
        return domain

    @api.constrains('kennel_observation_times')
    def _check_kennel_observation_times(self):
        for company in self:
            try:
                parse_times(company.kennel_observation_times)
            except ValueError as bad:
                raise ValidationError(self.env._(
                    '"%s" is not a time. Use 24-hour times like 09:00, 16:00.', bad))

    def _kennel_tz(self):
        """Timezone the kennel's daily task times are in: the company's, else the current user's."""
        self.ensure_one()
        return pytz.timezone(self.partner_id.tz or self.env.user.tz or 'UTC')

    def _kennel_observation_times(self):
        self.ensure_one()
        return parse_times(self.kennel_observation_times)
