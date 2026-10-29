from odoo import api, models


class PrintJob(models.Model):
    _name = 'print.job'
    _inherit = ['print.job', 'advanced.accounts.mixin']
    # Print jobs had no customer field: the Account and Contact are their own.
    _adv_partner_field = False

    # A job raised from a sales order starts with the order's customer.
    @api.depends('sale_order_id')
    def _compute_adv_contact_id(self):
        super()._compute_adv_contact_id()
        contacts = self.env['advanced.contact']._for_partners(self.sale_order_id.partner_id)
        for job in self:
            if not job.adv_contact_id and job.sale_order_id:
                job.adv_contact_id = contacts.get(job.sale_order_id.partner_id.id, False)

    @api.depends('sale_order_id')
    def _compute_adv_account_id(self):
        super()._compute_adv_account_id()
        accounts = self.env['advanced.account']._for_partners(self.sale_order_id.partner_id)
        for job in self:
            if not job.adv_account_id and job.sale_order_id:
                job.adv_account_id = accounts.get(job.sale_order_id.partner_id.id, False)
