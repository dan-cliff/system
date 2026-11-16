from odoo import fields, models


class CloseSubscriptionWizard(models.TransientModel):
    _name = 'close.reason.wizard'
    _description = 'Close Subscription'

    close_reason_id = fields.Many2one('sale.subscription.close.reason', string='Reason')

    def button_confirm(self):
        subscription = self.env['sale.subscription'].browse(self.env.context.get('active_id'))
        subscription.close_subscription(self.close_reason_id.id)
        return {'type': 'ir.actions.act_window_close'}


class PauseSubscriptionWizard(models.TransientModel):
    _name = 'sale.subscription.pause.wizard'
    _description = 'Pause Subscription'

    paused_until = fields.Date(string='Resume On',
                               help="The day the subscription is resumed. Leave empty to pause it until it is "
                                    "resumed by hand.")

    def button_confirm(self):
        subscription = self.env['sale.subscription'].browse(self.env.context.get('active_id'))
        subscription.action_pause(paused_until=self.paused_until or None)
        return {'type': 'ir.actions.act_window_close'}
