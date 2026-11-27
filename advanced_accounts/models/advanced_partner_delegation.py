from odoo import api, models


class AdvancedPartnerDelegation(models.AbstractModel):
    """Accounts and Contacts keep their details on a res.partner (``_inherits``),
    so every app that still works with partners (invoices, emails, the portal,
    users) sees the same name, email, phone and address.

    The partner is written with sudo() after checking access on the Account or
    Contact itself, so the Advanced Accounts permissions decide who may edit,
    not the partner access rights of the standard Contacts app."""
    _name = 'advanced.partner.delegation'
    _description = 'Record kept on a partner'

    def _split_partner_vals(self, vals):
        own, partner = {}, {}
        for name, value in vals.items():
            field = self._fields.get(name)
            (partner if field and field.inherited else own)[name] = value
        return own, partner

    def _prepare_partner_vals(self, own, partner_vals):
        """Values for a new partner, or for the partner given in ``own``."""
        return partner_vals

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env['res.partner'].sudo().with_context(advanced_accounts_no_adopt=True)
        own_list = []
        for vals in vals_list:
            own, partner_vals = self._split_partner_vals(vals)
            partner_vals = self._prepare_partner_vals(own, partner_vals)
            if own.get('partner_id'):
                if partner_vals:
                    Partner.browse(own['partner_id']).write(partner_vals)
            else:
                own['partner_id'] = Partner.create(partner_vals).id
            own_list.append(own)
        # Odoo may still write precomputed partner values (e.g. properties)
        # to the partner while creating: do that with sudo() too, then apply
        # the user's own create rules to the new records.
        self.check_access('create')
        records = super(AdvancedPartnerDelegation, self.sudo()).create(own_list).sudo(self.env.su)
        records.check_access('create')
        return records

    def write(self, vals):
        own, partner_vals = self._split_partner_vals(vals)
        result = super().write(own)
        checked = False
        for record in self:
            values = record._prepare_partner_vals(own, dict(partner_vals))
            if values:
                if not checked:
                    self.check_access('write')
                    checked = True
                record.partner_id.sudo().with_context(advanced_accounts_no_adopt=True).write(values)
        return result
