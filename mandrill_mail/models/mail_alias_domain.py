from odoo import api, models


class MailAliasDomain(models.Model):
    _inherit = 'mail.alias.domain'

    @api.model_create_multi
    def create(self, vals_list):
        domains = super().create(vals_list)
        self.env['mandrill.service']._schedule_route_sync()
        return domains

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'bounce_alias', 'catchall_alias'} & set(vals):
            self.env['mandrill.service']._schedule_route_sync()
        return res
