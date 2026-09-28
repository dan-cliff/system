from odoo import api, fields, models
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    kennel_resident_ids = fields.One2many(
        'kennel.resident', 'partner_id', string='Residents', groups='boarding_kennel_manager.group_kennel_keeper',
    )
    kennel_resident_count = fields.Integer(
        compute='_compute_kennel_resident_count', groups='boarding_kennel_manager.group_kennel_keeper',
    )

    @api.depends('kennel_resident_ids')
    def _compute_kennel_resident_count(self):
        for partner in self:
            partner.kennel_resident_count = len(partner.kennel_resident_ids)

    def action_view_kennel_residents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Residents'),
            'res_model': 'kennel.resident',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_kennel_portal_invite(self):
        """Open Odoo's portal access wizard for this customer, for users with the Customer Portal User permission."""
        self.ensure_one()
        if not self.env.user.has_group('boarding_kennel_manager.group_kennel_portal_user'):
            raise AccessError(self.env._('Only users with the Customer Portal User permission can invite customers.'))
        wizard = self.env['portal.wizard'].with_context(active_ids=self.ids).create({})
        return wizard._action_open_modal()
