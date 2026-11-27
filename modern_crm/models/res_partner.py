from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    modern_opportunity_ids = fields.One2many('modern.crm.opportunity', 'partner_id', string='Opportunities')
    modern_opportunity_count = fields.Integer(compute='_compute_modern_opportunity_count')

    def _compute_modern_opportunity_count(self):
        Opportunity = self.env['modern.crm.opportunity']
        if not Opportunity.has_access('read'):
            self.modern_opportunity_count = 0
            return
        counts = dict(Opportunity._read_group(
            [('partner_id', 'child_of', self.commercial_partner_id.ids)],
            ['partner_id'], ['__count']))
        for partner in self:
            partner.modern_opportunity_count = sum(
                count for p, count in counts.items()
                if p.commercial_partner_id == partner.commercial_partner_id)

    def action_view_modern_opportunities(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('modern_crm.modern_crm_opportunity_action')
        action.update(domain=[('partner_id', 'child_of', self.commercial_partner_id.id)],
                      context={'default_partner_id': self.commercial_partner_id.id})
        return action
