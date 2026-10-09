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
        scope_domain = self.env.user.sudo()._get_org_scope_domain(model_name)
        if scope_domain is None:
            return domain
        return (domain & scope_domain).optimize(self.env[model_name])
