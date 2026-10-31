# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_compare, format_amount

APPROVAL_ACTIVITY = 'advanced_purchasing.mail_activity_purchasing_approval'
GROUP_APPROVE = 'advanced_purchasing.group_purchase_order_approve'
GROUP_APPROVE_ANY = 'advanced_purchasing.group_purchase_order_approve_any'


class PurchaseOrder(models.Model):
    """Approvals by Spend Level instead of Odoo's single approval amount.

    Confirming an order works out its route (``_purchasing_route``): the
    Spend Level its total falls in, whether it needs approval and who can
    give it. Orders that need approval wait in "To Approve" until one of their
    approvers (or a user with Approve Any) approves them or sends them back.
    advanced_purchasing_hr adds the buyer's spend delegation and their 1st to
    4th Up Managers.
    """
    _inherit = 'purchase.order'

    purchasing_spend_level_id = fields.Many2one(
        'advanced.purchasing.spend.level', string='Spend Level', readonly=True, copy=False,
        tracking=True, index='btree_not_null')
    purchasing_approval_needed = fields.Boolean('Approval Needed', readonly=True, copy=False)
    purchasing_approval_route = fields.Char('Approval Route', readonly=True, copy=False)
    purchasing_approver_ids = fields.Many2many(
        'res.users', 'purchase_order_purchasing_approver_rel', 'order_id', 'user_id',
        string='Approvers', readonly=True, copy=False)
    purchasing_approved_by_id = fields.Many2one(
        'res.users', string='Approved By', readonly=True, copy=False, tracking=True)
    purchasing_rejection_reason = fields.Text('Reason Sent Back', readonly=True, copy=False)
    purchasing_can_approve = fields.Boolean(compute='_compute_purchasing_can_approve')
    # What is still to be paid on a confirmed order: its total less what has been
    # paid on its posted vendor bills (and refunded on its credit notes). An
    # estimate: a bill covering several orders counts in full for each of them.
    purchasing_balance_owing = fields.Monetary(
        'Estimated Balance Owing', currency_field='company_currency_id',
        compute='_compute_purchasing_balance_owing', search='_search_purchasing_balance_owing',
        help="The order's total less what has been paid on its vendor bills, in the company's currency.")

    @api.depends('state', 'amount_total_cc', 'invoice_ids.state', 'invoice_ids.amount_residual_signed')
    def _compute_purchasing_balance_owing(self):
        for order in self:
            if order.state != 'purchase':
                order.purchasing_balance_owing = 0.0
                continue
            paid = 0.0
            for bill in order.sudo().invoice_ids.filtered(lambda move: move.state == 'posted'):
                settled = abs(bill.amount_total_signed) - abs(bill.amount_residual_signed)
                paid += -settled if bill.move_type == 'in_refund' else settled
            order.purchasing_balance_owing = max(order.amount_total_cc - paid, 0.0)

    def _search_purchasing_balance_owing(self, operator, value):
        if operator not in ('>', '>=', '<', '<=', '=', '!=') or not isinstance(value, (int, float)):
            return NotImplemented
        orders = self.search([('state', '=', 'purchase')])
        ops = {'>': lambda a: a > value, '>=': lambda a: a >= value, '<': lambda a: a < value,
               '<=': lambda a: a <= value, '=': lambda a: a == value, '!=': lambda a: a != value}
        return [('id', 'in', orders.filtered(lambda o: ops[operator](o.purchasing_balance_owing)).ids)]

    @api.model
    def retrieve_dashboard(self):
        """Adds the Estimated Balance Owing card: the confirmed orders still to be
        paid, in the current company's currency."""
        result = super().retrieve_dashboard()
        company = self.env.company
        currency = company.currency_id
        today = fields.Date.context_today(self)
        total = mine = 0.0
        for order in self.search([('state', '=', 'purchase')]):
            amount = order.company_currency_id._convert(order.purchasing_balance_owing, currency, company, today)
            total += amount
            if order.user_id == self.env.user:
                mine += amount
        result['global']['balance_owing'] = format_amount(self.env, total, currency)
        result['my']['balance_owing'] = format_amount(self.env, mine, currency)
        return result

    @api.depends('state', 'purchasing_approver_ids')
    @api.depends_context('uid')
    def _compute_purchasing_can_approve(self):
        user = self.env.user
        approve_any = user.has_group(GROUP_APPROVE_ANY)
        approve = user.has_group(GROUP_APPROVE)
        for order in self:
            order.purchasing_can_approve = order.state == 'to approve' and (
                approve_any or (approve and user in order.purchasing_approver_ids))

    # ------------------------------------------------------------
    # Approval route
    # ------------------------------------------------------------

    def _purchasing_amount(self):
        """The total the Spend Levels are compared with, in the company's currency."""
        self.ensure_one()
        return self.amount_total_cc

    def _purchasing_buyer(self):
        self.ensure_one()
        return self.user_id or self.create_uid or self.env.user

    def _purchasing_requester_limit(self):
        """The buyer's spend delegation in the company's currency, or None when
        it isn't known (advanced_purchasing_hr reads it from their employee)."""
        return None

    def _purchasing_central_approvers(self):
        """The users who can approve any order of this company."""
        self.ensure_one()
        group = self.env.ref(GROUP_APPROVE_ANY, raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        return group.sudo().all_user_ids.filtered(
            lambda user: not user.share and not user._is_superuser() and self.company_id in user.company_ids)

    def _purchasing_find_approvers(self, tier, amount):
        """(users, description) of who approves this order. ``tier`` is how many
        managers up the approval goes (1 to 4). Without Personnel there is no
        org chart, so it goes to the users with Approve Any."""
        return self._purchasing_central_approvers(), self.env._('Purchase Approvers (Purchase Orders: Approve Any)')

    def _purchasing_route(self):
        """{'level', 'needed', 'approvers', 'route'} for the order as it is now."""
        self.ensure_one()
        company = self.company_id
        amount = self._purchasing_amount()
        level = self.env['advanced.purchasing.spend.level']._level_for_amount(amount, company)
        tier = int(level.approver_level) if level else 0
        route = {'level': level, 'needed': False, 'approvers': self.env['res.users'], 'route': ''}
        limit = self._purchasing_requester_limit()
        if limit is not None:
            if float_compare(amount, limit, precision_rounding=company.currency_id.rounding) <= 0:
                route['route'] = self.env._("Within the buyer's spend delegation")
                return route
            # Over their own delegation: at least their manager has to approve.
            tier = max(tier, 1)
        if not tier:
            route['route'] = self.env._('No approval needed at this Spend Level')
            return route
        approvers, description = self._purchasing_find_approvers(tier, amount)
        route.update(needed=True, approvers=approvers, route=description)
        return route

    def _purchasing_store_route(self, route):
        self.ensure_one()
        self.sudo().write({
            'purchasing_spend_level_id': route['level'].id,
            'purchasing_approval_needed': route['needed'],
            'purchasing_approval_route': route['route'],
            'purchasing_approver_ids': [Command.set(route['approvers'].ids)],
        })

    def _purchasing_user_can_approve(self, route, user=None):
        user = user or self.env.user
        if not route['needed'] or user.has_group(GROUP_APPROVE_ANY):
            return True
        return user in route['approvers'] and user.has_group(GROUP_APPROVE)

    def _purchasing_request_approval(self):
        """Give each approver an activity for the orders waiting for them."""
        for order in self:
            order.sudo().activity_unlink([APPROVAL_ACTIVITY])
            for user in order.purchasing_approver_ids:
                order.sudo().activity_schedule(
                    APPROVAL_ACTIVITY, user_id=user.id,
                    note=self.env._('Approve %(order)s or send it back (%(route)s).',
                                    order=order.name, route=order.purchasing_approval_route))
            if not order.purchasing_approver_ids:
                order.sudo().message_post(body=self.env._(
                    'No one can approve this order yet: a Purchasing Administrator can approve it, or give '
                    'someone the Purchase Orders: Approve Any permission.'))

    def _approval_allowed(self):
        """Replaces Odoo's single approval amount with the order's route."""
        self.ensure_one()
        if self.env.context.get('purchasing_approval_checked'):
            return True
        return self._purchasing_user_can_approve(self._purchasing_route())

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def button_confirm(self):
        to_confirm = self.filtered(lambda order: order.state in ('draft', 'sent'))
        for order in to_confirm:
            order._purchasing_store_route(order._purchasing_route())
        result = super().button_confirm()
        to_confirm.filtered(lambda order: order.state == 'to approve')._purchasing_request_approval()
        return result

    def button_approve(self, force=False):
        if self.env.context.get('purchasing_approval_checked'):
            return super().button_approve(force=force)
        orders = self.filtered(lambda order: order.state in ('draft', 'sent', 'to approve'))
        needed = self.browse()
        for order in orders:
            route = order._purchasing_route()
            if not order._purchasing_user_can_approve(route):
                approvers = ', '.join(route['approvers'].mapped('name')) or self.env._('a Purchasing Administrator')
                raise UserError(self.env._(
                    '%(order)s needs approval by %(approvers)s (%(route)s).',
                    order=order.name, approvers=approvers, route=route['route']))
            if route['needed']:
                needed |= order
        # Approvers may not be able to edit the order themselves: the check above is the permission.
        result = super(PurchaseOrder, orders.sudo().with_context(purchasing_approval_checked=True)).button_approve(force=force)
        if needed:
            needed.sudo().write({'purchasing_approved_by_id': self.env.user.id, 'purchasing_rejection_reason': False})
            needed.sudo().activity_feedback([APPROVAL_ACTIVITY], user_id=self.env.user.id,
                                            feedback=self.env._('Approved'))
            needed.sudo().activity_unlink([APPROVAL_ACTIVITY])
        return result

    def _purchasing_send_back(self, reason):
        """Return orders waiting for approval to the buyer, with a reason."""
        for order in self:
            if order.state != 'to approve':
                raise UserError(self.env._('%s is not waiting for approval.', order.name))
            if not order._purchasing_user_can_approve(order._purchasing_route()):
                raise UserError(self.env._('You cannot approve %s, so you cannot send it back.', order.name))
        for order in self:
            order.sudo().activity_unlink([APPROVAL_ACTIVITY])
            order.sudo().with_context(purchasing_no_reroute=True).write({
                'state': 'draft',
                'purchasing_rejection_reason': reason,
                'purchasing_approver_ids': [Command.clear()],
                'purchasing_approval_needed': False,
            })
            order.sudo().message_post(body=Markup('<p>%s</p><p>%s</p>') % (
                self.env._('Sent back by %s:', self.env.user.name), reason))
            order.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=order._purchasing_buyer().id,
                summary=self.env._('Purchase order sent back'), note=reason)

    def action_purchasing_send_back(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Send Back'),
            'res_model': 'advanced.purchasing.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_ids': self.ids},
        }

    def button_draft(self):
        result = super().button_draft()
        self.sudo().activity_unlink([APPROVAL_ACTIVITY])
        self.sudo().write({'purchasing_approver_ids': [Command.clear()], 'purchasing_approved_by_id': False,
                           'purchasing_approval_needed': False})
        return result

    def button_cancel(self):
        result = super().button_cancel()
        self.sudo().activity_unlink([APPROVAL_ACTIVITY])
        return result

    def write(self, vals):
        # An order waiting for approval whose total changes is routed again.
        waiting = self.filtered(lambda order: order.state == 'to approve')
        before = {order.id: order.amount_total_cc for order in waiting}
        result = super().write(vals)
        if waiting and not self.env.context.get('purchasing_no_reroute'):
            changed = waiting.filtered(
                lambda order: order.state == 'to approve'
                and order.company_id.currency_id.compare_amounts(order.amount_total_cc, before[order.id]))
            for order in changed:
                order._purchasing_store_route(order._purchasing_route())
            changed._purchasing_request_approval()
        return result

    # ------------------------------------------------------------
    # PDF and email
    # ------------------------------------------------------------

    def action_print_purchasing_order(self):
        """Download the Purchase Order PDF straight away, in the order company's
        branding (config=False skips the document layout wizard)."""
        return self.env.ref('advanced_purchasing.action_report_purchasing_order').report_action(self, config=False)

    def print_quotation(self):
        self.filtered(lambda order: order.state == 'draft').write({'state': 'sent'})
        return self.env.ref('purchase.report_purchase_quotation').report_action(self, config=False)

    def action_rfq_send(self):
        action = super().action_rfq_send()
        if not self.env.context.get('send_rfq'):
            template = self.env.ref('advanced_purchasing.email_template_purchasing_order', raise_if_not_found=False)
            if template:
                action['context']['default_template_id'] = template.id
        return action
