# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import float_compare

from odoo.addons.advanced_purchasing.models.purchase_order import GROUP_APPROVE
from odoo.addons.advanced_purchasing.models.spend_level import APPROVER_LEVELS

UP_MANAGER_LABELS = dict(APPROVER_LEVELS)


class PurchaseOrder(models.Model):
    """The buyer's spend delegation and their Up Managers decide the approval route."""
    _inherit = 'purchase.order'

    purchasing_buyer_employee_id = fields.Many2one(
        'hr.employee', string="Buyer's Employee", compute='_compute_purchasing_buyer_limit', compute_sudo=True)
    purchasing_buyer_limit = fields.Monetary(
        "Buyer's Spend Limit", currency_field='company_currency_id',
        compute='_compute_purchasing_buyer_limit', compute_sudo=True)
    purchasing_buyer_unlimited = fields.Boolean(
        "Buyer Has No Spend Limit", compute='_compute_purchasing_buyer_limit', compute_sudo=True)

    @api.depends('user_id', 'create_uid', 'company_id')
    def _compute_purchasing_buyer_limit(self):
        for order in self:
            employee = order._purchasing_requester_employee()
            limit = employee._purchase_spend_limit() if employee else 0.0
            order.purchasing_buyer_employee_id = employee
            order.purchasing_buyer_unlimited = limit == float('inf')
            order.purchasing_buyer_limit = 0.0 if limit == float('inf') else limit

    def _purchasing_requester_employee(self):
        self.ensure_one()
        buyer = self._purchasing_buyer()
        return buyer.sudo().with_company(self.company_id).employee_id

    def _purchasing_requester_limit(self):
        employee = self._purchasing_requester_employee()
        if not employee:
            return super()._purchasing_requester_limit()
        return employee._purchase_spend_limit()

    def _purchasing_find_approvers(self, tier, amount):
        """The buyer's Up Manager the Spend Level names, or the next one up who
        can approve: a manager needs a user with Purchase Orders: Approve and,
        when the company escalates, a delegation covering the order. Fewer
        managers than the level asks for: the highest one."""
        employee = self._purchasing_requester_employee()
        if not employee:
            return super()._purchasing_find_approvers(tier, amount)
        chain = list(employee._purchase_manager_chain())
        if not chain:
            approvers, description = super()._purchasing_find_approvers(tier, amount)
            return approvers, self.env._('%(route)s - the buyer has no Manager', route=description)
        start = min(tier, len(chain)) - 1
        escalate = self.company_id.purchasing_escalate_delegation
        rounding = self.company_id.currency_id.rounding
        skipped = []
        for position in range(start, len(chain)):
            manager = chain[position]
            label = UP_MANAGER_LABELS[str(position + 1)]
            user = manager.user_id
            if not user or not user.has_group(GROUP_APPROVE):
                skipped.append(self.env._('%(label)s %(name)s cannot approve purchases', label=label, name=manager.name))
                continue
            if escalate and float_compare(manager._purchase_spend_limit(), amount, precision_rounding=rounding) < 0:
                skipped.append(self.env._("%(label)s %(name)s's delegation is too low", label=label, name=manager.name))
                continue
            description = self.env._('%(label)s: %(name)s', label=label, name=manager.name)
            if position != tier - 1:
                description += ' (%s)' % '; '.join(skipped or [self.env._('the highest manager')])
            return user, description
        approvers, description = super()._purchasing_find_approvers(tier, amount)
        return approvers, '%s (%s)' % (description, '; '.join(skipped))
