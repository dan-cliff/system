from odoo import _, models
from odoo.exceptions import UserError

from ..hooks import OM_MODULES


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_install(self):
        """ The Odoo Mates accounting modules define the same models as
        Accounting: loading both would make one of them lose its fields. """
        result = super().button_install()
        clashing = self.search([('name', 'in', OM_MODULES), ('state', '=', 'to install')])
        if clashing:
            raise UserError(_(
                "%(modules)s cannot be installed: Accounting already provides it, with the same records.",
                modules=", ".join(clashing.mapped('shortdesc')),
            ))
        return result
