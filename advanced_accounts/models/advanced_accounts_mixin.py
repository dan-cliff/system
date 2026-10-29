from odoo import api, fields, models

CONTACT_DOMAIN = "[('account_id', '=', adv_account_id)] if adv_account_id else []"


class AdvancedAccountsMixin(models.AbstractModel):
    """An Account and a Contact on a record, standing in for its partner field.

    Pick an Account and the Contact list only shows that Account's Contacts;
    pick a Contact first and its Account fills in. The record's own partner
    field(s) keep following them, so the app (prices, invoices, emails,
    portal) works as before; and when code sets the partner, the Account and
    Contact follow it.

    Set on the model:

    - ``_adv_partner_field``: the partner field that gets the Contact's partner,
      or the Account's when there is no Contact. False when the record has no
      partner field (the Account and Contact are then fields of their own).
    - ``_adv_account_partner_field``: a separate partner field holding the
      Account (e.g. CRM opportunities keep the Account in ``partner_id`` and the
      Contact in ``contact_id``).
    """
    _name = 'advanced.accounts.mixin'
    _description = 'Account and Contact'
    _adv_partner_field = 'partner_id'
    _adv_account_partner_field = False

    adv_account_id = fields.Many2one(
        'advanced.account', string='Account', index='btree_not_null', ondelete='set null',
        compute='_compute_adv_account_id', store=True, readonly=False, precompute=True)
    adv_contact_id = fields.Many2one(
        'advanced.contact', string='Contact', index='btree_not_null', ondelete='set null',
        domain=CONTACT_DOMAIN,
        compute='_compute_adv_contact_id', store=True, readonly=False, precompute=True)

    def _adv_partner_fields(self):
        return [name for name in (self._adv_account_partner_field, self._adv_partner_field) if name]

    @api.depends(lambda self: self._adv_partner_fields())
    def _compute_adv_contact_id(self):
        field = self._adv_partner_field
        if not field or self._adv_account_partner_field == field:
            for record in self:
                record.adv_contact_id = record.adv_contact_id
            return
        contacts = self.env['advanced.contact']._for_partners(self[field])
        for record in self:
            partner = record[field]
            if record.adv_contact_id and record.adv_contact_id.partner_id == partner:
                continue
            record.adv_contact_id = contacts.get(partner.id, False)

    @api.depends(lambda self: self._adv_partner_fields() + ['adv_contact_id'])
    def _compute_adv_account_id(self):
        field = self._adv_account_partner_field or self._adv_partner_field
        accounts = self.env['advanced.account']._for_partners(self[field]) if field else {}
        for record in self:
            if record.adv_contact_id.account_id:
                record.adv_account_id = record.adv_contact_id.account_id
            elif field:
                record.adv_account_id = accounts.get(record[field].id, False)
            else:
                record.adv_account_id = record.adv_account_id

    def _adv_partner_values(self, account, contact):
        """The partner field values for this Account and Contact."""
        account = account or contact.account_id
        values = {}
        if self._adv_account_partner_field:
            values[self._adv_account_partner_field] = account.partner_id.id
            if self._adv_partner_field and self._adv_partner_field != self._adv_account_partner_field:
                values[self._adv_partner_field] = contact.partner_id.id
        elif self._adv_partner_field:
            values[self._adv_partner_field] = (contact or account).partner_id.id
        return values

    def _adv_update_partners(self):
        for field, value in self._adv_partner_values(self.adv_account_id, self.adv_contact_id).items():
            if self[field].id != value:
                self[field] = value

    @api.onchange('adv_account_id')
    def _onchange_adv_account_id(self):
        if self.adv_contact_id and self.adv_account_id and self.adv_contact_id.account_id != self.adv_account_id:
            self.adv_contact_id = False
        self._adv_update_partners()

    @api.onchange('adv_contact_id')
    def _onchange_adv_contact_id(self):
        if self.adv_contact_id.account_id:
            self.adv_account_id = self.adv_contact_id.account_id
        self._adv_update_partners()

    def _adv_fill_partner_vals(self, vals, record=None):
        """Called with values that set the Account or Contact but none of the
        partner fields (imports, code): add the partner fields they imply."""
        if not ('adv_account_id' in vals or 'adv_contact_id' in vals):
            return vals
        if any(name in vals for name in self._adv_partner_fields()):
            return vals
        Account, Contact = self.env['advanced.account'], self.env['advanced.contact']
        contact = Contact.browse(vals['adv_contact_id']) if 'adv_contact_id' in vals else (
            record.adv_contact_id if record else Contact)
        account = Account.browse(vals['adv_account_id']) if 'adv_account_id' in vals else (
            record.adv_account_id if record else Account)
        if 'adv_account_id' in vals and contact.account_id and contact.account_id != account:
            contact = Contact
            vals['adv_contact_id'] = False
        if contact.account_id:
            account = contact.account_id
            vals.setdefault('adv_account_id', account.id)
        return dict(vals, **self._adv_partner_values(account.sudo(), contact.sudo()))

    def _adv_adopt(self):
        """Records whose partner has no Account or Contact yet (a partner made
        outside Advanced Accounts): give it one, then link it here."""
        fields_ = self._adv_partner_fields()
        if not fields_ or self.env.context.get('advanced_accounts_no_adopt'):
            return
        todo = self.filtered(lambda r: not r.adv_account_id and not r.adv_contact_id
                             and any(r[f] for f in fields_))
        if not todo:
            return
        partners = self.env['res.partner'].concat(*(todo.mapped(f) for f in fields_))
        self.env['advanced.contact']._adopt_partners(partners)
        self.env.add_to_compute(self._fields['adv_contact_id'], todo)
        self.env.add_to_compute(self._fields['adv_account_id'], todo)
        todo._recompute_recordset(['adv_contact_id', 'adv_account_id'])

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create([self._adv_fill_partner_vals(dict(vals)) for vals in vals_list])
        records._adv_adopt()
        return records

    def write(self, vals):
        if ('adv_account_id' in vals or 'adv_contact_id' in vals) and len(self) > 1 \
                and not any(name in vals for name in self._adv_partner_fields()):
            for record in self:
                record.write(dict(vals))
            return True
        result = super().write(self._adv_fill_partner_vals(dict(vals), self[:1] or None))
        if any(name in vals for name in self._adv_partner_fields()):
            self._adv_adopt()
        return result
