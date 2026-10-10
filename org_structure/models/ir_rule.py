from odoo import api, models, tools
from odoo.fields import Domain
from odoo.tools import config


class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    @tools.conditional(
        'xml' not in config['dev_mode'],
        tools.ormcache('self.env.uid', 'self.env.su', 'model_name', 'mode',
                       'tuple(self._compute_domain_context_values())'),
    )
    def _compute_domain(self, model_name: str, mode: str = "read") -> Domain:
        domain = super()._compute_domain(model_name, mode)
        if self.env.su or not getattr(self.env[model_name], '_org_scoped', False):
            return domain
        user = self.env.user.sudo()
        scope_domain = user._get_org_scope_domain(model_name)
        if scope_domain is None:
            return domain
        if model_name == 'res.partner':
            # res.users inherits res.partner, so a hidden contact hides its
            # user: always show the user's own contact, every user's contact
            # and the companies' contacts.
            company_partners = self.env['res.company'].sudo().search([]).partner_id
            scope_domain = (
                scope_domain
                | Domain('id', 'in', (user.partner_id | company_partners).ids)
                | Domain('user_ids', '!=', False)
            )
        return (domain & scope_domain).optimize(self.env[model_name])
