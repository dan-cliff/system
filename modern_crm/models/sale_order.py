from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    modern_opportunity_id = fields.Many2one(
        'modern.crm.opportunity', string='Opportunity', index='btree_not_null', copy=False,
        domain="[('company_id', '=', company_id)]")

    def action_confirm(self):
        res = super().action_confirm()
        # Salesforce: an opportunity is Closed Won once it is sold.
        won = self.filtered(lambda o: o.modern_opportunity_id and o.company_id.modern_crm_won_on_order)
        won.modern_opportunity_id.sudo().filtered(lambda o: not o.is_closed).action_set_won()
        return res

    def action_view_modern_opportunity(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'modern.crm.opportunity',
            'view_mode': 'form',
            'res_id': self.modern_opportunity_id.id,
        }
