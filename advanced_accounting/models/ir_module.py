from odoo import _, models
from odoo.exceptions import UserError

from ..hooks import TAKEN_OVER_MODULES


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_install(self):
        """ The Odoo Mates accounting modules and the Subscription management
        app (subscription_oca) define the same models as
        Accounting: loading both would make one of them lose its fields. """
        result = super().button_install()
        clashing = self.search([('name', 'in', TAKEN_OVER_MODULES), ('state', '=', 'to install')])
        if clashing:
            raise UserError(_(
                "%(modules)s cannot be installed: Accounting already provides it, with the same records.",
                modules=", ".join(clashing.mapped('shortdesc')),
            ))
        return result
