from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleSubscriptionTemplate(models.Model):
    """ How a subscription recurs and is billed. The recurrence, duration and
    invoicing mode are technical choices the code acts on, so they stay fixed
    selections (see CLAUDE.md > Choice fields). """
    _name = 'sale.subscription.template'
    _description = 'Subscription Template'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    code = fields.Char(help="Put in front of the subscriptions' references, e.g. MONTH/SUB00012.")
    description = fields.Text(string='Terms and Conditions',
                              help="Copied onto the subscriptions, and printed on their invoices.")
    recurring_interval = fields.Integer(string='Repeat Every', default=1)
    recurring_rule_type = fields.Selection([
        ('days', 'Day(s)'),
        ('weeks', 'Week(s)'),
        ('months', 'Month(s)'),
        ('years', 'Year(s)'),
    ], string='Recurrence', default='months', required=True)
    recurring_rule_boundary = fields.Selection([
        ('unlimited', 'Forever'),
        ('limited', 'Fixed'),
    ], string='Duration', default='unlimited', required=True)
    recurring_rule_count = fields.Integer(string='Number of Periods', default=1,
                                          help="How many periods a subscription with a fixed duration runs for.")
    invoicing_mode = fields.Selection([
        ('draft', 'Draft Invoice'),
        ('invoice', 'Posted Invoice'),
        ('invoice_send', 'Posted Invoice, Emailed'),
        ('sale_and_invoice', 'Sales Order and Posted Invoice'),
    ], string='Invoicing', default='draft', required=True,
        help="Draft Invoice: the invoice waits for someone to check and post it.\n"
             "Posted Invoice: the invoice is posted.\n"
             "Posted Invoice, Emailed: the invoice is posted and emailed to the customer.\n"
             "Sales Order and Posted Invoice: a sales order is confirmed for the period, and its invoice posted.")
    invoice_mail_template_id = fields.Many2one(
        'mail.template', string='Invoice Email', domain="[('model', '=', 'account.move')]",
        help="The email of the invoices. Leave empty for the standard invoice email.")
    product_ids = fields.One2many('product.template', 'subscription_template_id', string='Products')
    product_ids_count = fields.Integer(string='Product Count', compute='_compute_product_ids_count')
    subscription_ids = fields.One2many('sale.subscription', 'template_id', string='Subscriptions')
    subscription_count = fields.Integer(string='Subscription Count', compute='_compute_subscription_count')

    @api.constrains('recurring_interval', 'recurring_rule_count')
    def _check_positive(self):
        for template in self:
            if template.recurring_interval < 1:
                raise ValidationError(self.env._('A subscription template must repeat at least every 1 period.'))
            if template.recurring_rule_boundary == 'limited' and template.recurring_rule_count < 1:
                raise ValidationError(self.env._('A subscription with a fixed duration runs for at least 1 period.'))

    def _compute_product_ids_count(self):
        counts = dict(self.env['product.template']._read_group(
            [('subscription_template_id', 'in', self.ids)], ['subscription_template_id'], ['__count']))
        for template in self:
            template.product_ids_count = counts.get(template._origin, 0)

    def _compute_subscription_count(self):
        counts = dict(self.env['sale.subscription']._read_group(
            [('template_id', 'in', self.ids)], ['template_id'], ['__count']))
        for template in self:
            template.subscription_count = counts.get(template._origin, 0)

    def _get_date(self, date_start):
        """ The end of a subscription with a fixed duration started on `date_start`. """
        self.ensure_one()
        periods = (self.recurring_interval or 1) * (self.recurring_rule_count or 1)
        return date_start + relativedelta(**{self.recurring_rule_type or 'months': periods})

    def action_view_subscription_ids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_accounting.sale_subscription_action')
        action.update({
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        })
        return action

    def action_view_product_ids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'advanced_accounting.subscription_product_template_action')
        action.update({
            'domain': [('subscription_template_id', '=', self.id)],
            'context': {'default_subscribable': True, 'default_subscription_template_id': self.id},
        })
        return action
