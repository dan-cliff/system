from odoo import api, models


class MailAlias(models.Model):
    _inherit = 'mail.alias'

    @api.model_create_multi
    def create(self, vals_list):
        aliases = super().create(vals_list)
        if aliases.filtered('alias_name'):
            self.env['mandrill.service']._schedule_route_sync()
        return aliases

    def write(self, vals):
        res = super().write(vals)
        if {'alias_name', 'alias_domain_id'} & set(vals):
            self.env['mandrill.service']._schedule_route_sync()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['mandrill.service']._schedule_route_sync()
        return res
