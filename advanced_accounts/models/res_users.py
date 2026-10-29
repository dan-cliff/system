from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # A user built for a Contact shares the Contact's partner, so its name,
    # email and phone are the Contact's.
    adv_contact_id = fields.Many2one(
        'advanced.contact', string='Contact', compute='_compute_adv_contact_id', compute_sudo=True)

    @api.depends('partner_id')
    def _compute_adv_contact_id(self):
        contacts = self.env['advanced.contact']._for_partners(self.partner_id)
        for user in self:
            user.adv_contact_id = contacts.get(user.partner_id.id, False)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        # Portal users (website sign-ups, invitations) are people outside the
        # company: give them a Contact. Internal users are employees, not Contacts.
        portal = users.filtered('share')
        if portal:
            self.env['advanced.contact']._adopt_partners(portal.partner_id)
        return users

    def action_open_adv_contact(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'advanced.contact',
                'res_id': self.adv_contact_id.id, 'view_mode': 'form'}
