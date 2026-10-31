# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError

# The Purchases Rules fields only Spend Delegations: Manage may change.
PURCHASE_RULE_FIELDS = {
    'purchase_spend_level_id', 'purchase_custom_limit_enabled', 'purchase_custom_limit',
    'purchase_delegation_date_from', 'purchase_delegation_date_to', 'purchase_delegation_notes',
}
UP_MANAGERS = 4


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    purchase_spend_level_id = fields.Many2one(
        'advanced.purchasing.spend.level', string='Spend Level Delegation', groups='hr.group_hr_user',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='The Spend Level this employee may spend up to without approval. Orders above it go to '
             'their Up Managers.')
    purchase_custom_limit_enabled = fields.Boolean(
        'Custom Spend Limit', groups='hr.group_hr_user',
        help="Use an amount of the employee's own instead of their Spend Level's limit.")
    purchase_custom_limit = fields.Monetary(
        'Custom Limit', currency_field='purchase_currency_id', groups='hr.group_hr_user')
    purchase_currency_id = fields.Many2one(related='company_id.currency_id', string='Purchase Currency')
    purchase_spend_limit = fields.Monetary(
        'Spend Limit', currency_field='purchase_currency_id', compute='_compute_purchase_spend_limit',
        groups='hr.group_hr_user',
        help='What the employee can spend on one order without approval today, in the company currency.')
    purchase_spend_unlimited = fields.Boolean(
        'No Spend Limit', compute='_compute_purchase_spend_limit', groups='hr.group_hr_user')
    purchase_delegation_date_from = fields.Date('Delegation Valid From', groups='hr.group_hr_user')
    purchase_delegation_date_to = fields.Date('Delegation Valid Until', groups='hr.group_hr_user')
    purchase_delegation_in_force = fields.Boolean(
        'Delegation In Force', compute='_compute_purchase_spend_limit', groups='hr.group_hr_user')
    purchase_delegation_notes = fields.Html('Delegation Notes', groups='hr.group_hr_user')
    purchase_manager_1_id = fields.Many2one(
        'hr.employee', string='1st Up Manager', compute='_compute_purchase_managers', groups='hr.group_hr_user')
    purchase_manager_2_id = fields.Many2one(
        'hr.employee', string='2nd Up Manager', compute='_compute_purchase_managers', groups='hr.group_hr_user')
    purchase_manager_3_id = fields.Many2one(
        'hr.employee', string='3rd Up Manager', compute='_compute_purchase_managers', groups='hr.group_hr_user')
    purchase_manager_4_id = fields.Many2one(
        'hr.employee', string='4th Up Manager', compute='_compute_purchase_managers', groups='hr.group_hr_user')
    purchase_can_edit_rules = fields.Boolean(compute='_compute_purchase_can_edit_rules')

    @api.depends('purchase_spend_level_id.amount_limit', 'purchase_spend_level_id.unlimited',
                 'purchase_custom_limit_enabled', 'purchase_custom_limit',
                 'purchase_delegation_date_from', 'purchase_delegation_date_to')
    def _compute_purchase_spend_limit(self):
        for employee in self:
            limit = employee._purchase_spend_limit()
            employee.purchase_delegation_in_force = employee._purchase_delegation_in_force()
            employee.purchase_spend_unlimited = limit == float('inf')
            employee.purchase_spend_limit = 0.0 if limit == float('inf') else limit

    @api.depends('parent_id', 'parent_id.parent_id', 'parent_id.parent_id.parent_id',
                 'parent_id.parent_id.parent_id.parent_id')
    def _compute_purchase_managers(self):
        for employee in self:
            chain = employee._purchase_manager_chain()
            for position in range(UP_MANAGERS):
                employee[f'purchase_manager_{position + 1}_id'] = chain[position] if len(chain) > position else False

    @api.depends_context('uid')
    def _compute_purchase_can_edit_rules(self):
        can_edit = self.env.user.has_group('advanced_purchasing.group_spend_delegation_manage')
        for employee in self:
            employee.purchase_can_edit_rules = can_edit

    def _purchase_delegation_in_force(self, date=None):
        self.ensure_one()
        employee = self.sudo()
        date = date or fields.Date.context_today(self)
        if employee.purchase_delegation_date_from and date < employee.purchase_delegation_date_from:
            return False
        if employee.purchase_delegation_date_to and date > employee.purchase_delegation_date_to:
            return False
        return bool(employee.purchase_custom_limit_enabled or employee.purchase_spend_level_id)

    def _purchase_spend_limit(self, date=None):
        """What the employee may spend on one order without approval, in the
        company's currency: 0 without a delegation in force, infinite for a
        Spend Level with no upper limit."""
        self.ensure_one()
        employee = self.sudo()
        if not employee._purchase_delegation_in_force(date):
            return 0.0
        if employee.purchase_custom_limit_enabled:
            return employee.purchase_custom_limit
        return employee.purchase_spend_level_id._spend_limit()

    def _purchase_manager_chain(self):
        """The employee's 1st to 4th Up Managers (Manager, their Manager, ...)."""
        self.ensure_one()
        chain = self.env['hr.employee']
        manager = self.sudo().parent_id
        while manager and len(chain) < UP_MANAGERS and manager not in chain and manager != self:
            chain |= manager
            manager = manager.parent_id
        return chain

    def _purchase_check_rule_access(self, vals):
        if PURCHASE_RULE_FIELDS & set(vals) and not self.env.su \
                and not self.env.user.has_group('advanced_purchasing.group_spend_delegation_manage'):
            raise AccessError(self.env._(
                'Only users with the Spend Delegations: Manage permission can change Purchases Rules.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._purchase_check_rule_access(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._purchase_check_rule_access(vals)
        return super().write(vals)
