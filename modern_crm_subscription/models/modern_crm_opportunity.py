from odoo import api, fields, models


class ModernCrmOpportunity(models.Model):
    _inherit = 'modern.crm.opportunity'

    subscription_count = fields.Integer(compute='_compute_subscription_count')

    def _get_subscriptions(self):
        # Subscriptions follow Sales access, which CRM users may not have.
        return self.env['sale.subscription'].sudo().search([('sale_order_id', 'in', self.sudo().order_ids.ids)])

    @api.depends('order_ids.state')
    def _compute_subscription_count(self):
        for opportunity in self:
            opportunity.subscription_count = len(opportunity._get_subscriptions())

    def action_view_subscriptions(self):
        self.ensure_one()
        subscriptions = self._get_subscriptions()
        action = self.env['ir.actions.act_window']._for_xml_id('subscription_oca.sale_subscription_action')
        action['context'] = {'create': False}
        if len(subscriptions) == 1:
            action.update(views=[(False, 'form')], view_mode='form', res_id=subscriptions.id)
        else:
            action['domain'] = [('id', 'in', subscriptions.ids)]
        return action


class ModernCrmOpportunityLine(models.Model):
    _inherit = 'modern.crm.opportunity.line'

    subscribable = fields.Boolean(related='product_id.subscribable', string='Recurring')
