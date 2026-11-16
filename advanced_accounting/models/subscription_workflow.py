"""The workflow permissions of Subscriptions (see workflow_access.py).

Starting, pausing, resuming and closing a subscription (including moving it to
another stage) need "Subscriptions: Start, Pause and Close"; invoicing one by
hand needs "Subscriptions: Create Invoices". The action then runs with sudo().
The scheduled action runs as the superuser, and the subscriptions started by a
confirmed sales order are made as the superuser too (see subscription_links.py).
"""
from odoo import _, models

from .workflow_access import _check_workflow


class SaleSubscription(models.Model):
    _inherit = 'sale.subscription'

    def write(self, vals):
        if 'stage_id' in vals:
            _check_workflow(self, 'group_subscription_manage', _('change the stage of subscriptions'))
            return super(SaleSubscription, self.sudo()).write(vals)
        return super().write(vals)

    def action_start_subscription(self):
        _check_workflow(self, 'group_subscription_manage', _('start subscriptions'))
        return super(SaleSubscription, self.sudo()).action_start_subscription()

    def close_subscription(self, close_reason_id=False):
        _check_workflow(self, 'group_subscription_manage', _('close subscriptions'))
        return super(SaleSubscription, self.sudo()).close_subscription(close_reason_id)

    def action_close_subscription(self):
        _check_workflow(self, 'group_subscription_manage', _('close subscriptions'))
        return super().action_close_subscription()

    def action_open_pause_wizard(self):
        _check_workflow(self, 'group_subscription_manage', _('pause subscriptions'))
        return super().action_open_pause_wizard()

    def action_pause(self, paused_until=None):
        _check_workflow(self, 'group_subscription_manage', _('pause subscriptions'))
        return super(SaleSubscription, self.sudo()).action_pause(paused_until)

    def action_resume(self, automatic=False):
        _check_workflow(self, 'group_subscription_manage', _('resume subscriptions'))
        return super(SaleSubscription, self.sudo()).action_resume(automatic)

    def manual_invoice(self):
        _check_workflow(self, 'group_subscription_invoice', _('invoice subscriptions'))
        return super(SaleSubscription, self.sudo()).manual_invoice()

    def generate_invoice(self):
        _check_workflow(self, 'group_subscription_invoice', _('invoice subscriptions'))
        return super(SaleSubscription, self.sudo()).generate_invoice()
