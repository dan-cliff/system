from odoo import Command, api, models


class SignrRequest(models.Model):
    _name = 'signr.request'
    _inherit = ['signr.request', 'advanced.accounts.mixin']
    # Requests had no customer field: the Account and Contact are their own.
    # Signers stay partners, since they are often our own users or employees.
    _adv_partner_field = False

    @api.onchange('adv_contact_id')
    def _onchange_adv_contact_signer(self):
        # The customer signs first when the draft has no signers yet.
        if self.state == 'draft' and self.adv_contact_id and not self.signer_ids:
            self.signer_ids = [Command.create({
                'partner_id': self.adv_contact_id.partner_id.id,
                'role': self.env._('Customer'),
            })]
