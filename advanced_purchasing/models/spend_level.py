# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

# Who approves an order in a Spend Level. A fixed list (CLAUDE.md > Choice
# fields exception): the approval code walks that many managers up the org chart.
APPROVER_LEVELS = [
    ('0', 'No Approval Needed'),
    ('1', '1st Up Manager'),
    ('2', '2nd Up Manager'),
    ('3', '3rd Up Manager'),
    ('4', '4th Up Manager'),
]


class PurchasingSpendLevel(models.Model):
    """A band of order value and who has to approve orders in it.

    An order falls in the lowest level whose Spend Limit covers its total (in
    the company's currency); above every limit it falls in the highest level.
    With Personnel, a level is also the spend delegation an employee holds.
    """
    _name = 'advanced.purchasing.spend.level'
    _description = 'Spend Level'
    _order = 'sequence, unlimited, amount_limit, id'

    name = fields.Char('Spend Level', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Blank: the level is shared by every company (a company with levels of its
    # own only uses those).
    company_id = fields.Many2one('res.company', string='Company', index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id')
    amount_limit = fields.Monetary(
        'Spend Limit', currency_field='currency_id',
        help="Orders up to this total (taxes included, in the company's currency) fall in this level.")
    unlimited = fields.Boolean(
        'No Upper Limit', help='The level covers every order above the other levels.')
    approver_level = fields.Selection(
        APPROVER_LEVELS, string='Approved By', required=True, default='1',
        help="Who approves orders in this level. Without Personnel, any level that needs approval "
             "sends the order to the users with Purchase Orders: Approve Any.")
    description = fields.Text('Description')

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_currency_id(self):
        for level in self:
            level.currency_id = (level.company_id or self.env.company).currency_id

    @api.constrains('amount_limit', 'unlimited')
    def _check_amount_limit(self):
        for level in self:
            if not level.unlimited and level.amount_limit < 0:
                raise ValidationError(self.env._('The Spend Limit of "%s" cannot be negative.', level.name))

    @api.model
    def _levels_for_company(self, company):
        """The active levels that apply to a company, lowest limit first."""
        levels = self.sudo().search([('company_id', '=', company.id)])
        if not levels:
            levels = self.sudo().search([('company_id', '=', False)])
        return levels.sorted(lambda level: (level.unlimited, level.amount_limit, level.sequence, level.id))

    @api.model
    def _level_for_amount(self, amount, company):
        """The Spend Level an order total (in the company's currency) falls in."""
        levels = self._levels_for_company(company)
        rounding = company.currency_id.rounding
        for level in levels:
            if level.unlimited or float_compare(amount, level.amount_limit, precision_rounding=rounding) <= 0:
                return level
        return levels[-1:]

    def _spend_limit(self):
        """The level's limit as a number: infinite when it has no upper limit."""
        self.ensure_one()
        return float('inf') if self.unlimited else self.amount_limit
