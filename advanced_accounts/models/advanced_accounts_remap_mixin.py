from odoo import api, models


class AdvancedAccountsRemapMixin(models.AbstractModel):
    """Account or Contact fields standing in for a record's partner fields,
    one for one (e.g. an asset's Supplier and Manufacturer become Accounts and
    its Owner a Contact). Use it when a record has several partner fields or
    isn't about one customer; ``advanced.accounts.mixin`` covers the usual
    single Account + Contact.

    Declare each new Many2one (to ``advanced.account`` or ``advanced.contact``)
    with ``compute='_compute_adv_remap'``, ``store=True``, ``readonly=False``,
    ``precompute=True``, and list it in ``_adv_remap``:
    ``{new field: partner field it stands in for}``. Picking the Account or
    Contact sets the partner field (so code and reports reading it keep
    working); setting the partner field (in code) moves the Account or Contact.
    A partner field of False makes the new field a plain field of its own.
    """
    _name = 'advanced.accounts.remap.mixin'
    _description = 'Accounts and Contacts in place of partner fields'
    _adv_remap = {}

    @api.depends(lambda self: [old for old in self._adv_remap.values() if old])
    def _compute_adv_remap(self):
        for new, old in self._adv_remap.items():
            if not old:
                for record in self:
                    record[new] = record[new]
                continue
            comodel = self.env[self._fields[new].comodel_name]
            mapping = comodel._for_partners(self[old])
            for record in self:
                record[new] = mapping.get(record[old].id, False)

    def _adv_remap_push(self, new):
        """Onchange helper: copy the picked Account or Contact to its partner field."""
        old = self._adv_remap[new]
        if old and self[old] != self[new].partner_id:
            self[old] = self[new].partner_id

    def _adv_remap_fill(self, vals):
        for new, old in self._adv_remap.items():
            if old and new in vals and old not in vals:
                record = self.env[self._fields[new].comodel_name].sudo().browse(vals[new])
                vals[old] = record.partner_id.id
        return vals

    def _adv_remap_adopt(self, names):
        olds = [old for new, old in self._adv_remap.items() if old and old in names]
        if not olds or self.env.context.get('advanced_accounts_no_adopt'):
            return
        partners = self.env['res.partner'].concat(*(self.mapped(old) for old in olds))
        if not partners:
            return
        self.env['advanced.contact']._adopt_partners(partners)
        news = [new for new, old in self._adv_remap.items() if old in olds]
        for new in news:
            self.env.add_to_compute(self._fields[new], self)
        self._recompute_recordset(news)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create([self._adv_remap_fill(dict(vals)) for vals in vals_list])
        records._adv_remap_adopt(list(self._adv_remap.values()))
        return records

    def write(self, vals):
        vals = self._adv_remap_fill(dict(vals))
        result = super().write(vals)
        self._adv_remap_adopt(vals.keys())
        return result
