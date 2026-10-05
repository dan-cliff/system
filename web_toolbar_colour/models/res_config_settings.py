from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Not a related field: related fields are written through to the company
    # when the settings record is created, before execute() runs, which would
    # hide the change from the reload check below.
    toolbar_color = fields.Char(string='Toolbar Colour')

    @api.model
    def get_values(self):
        res = super().get_values()
        res['toolbar_color'] = self.env.company.toolbar_color or False
        return res

    def set_values(self):
        super().set_values()
        if (self.company_id.toolbar_color or False) != (self.toolbar_color or False):
            self.company_id.toolbar_color = self.toolbar_color or False

    def execute(self):
        # The toolbar colour is read once when the web client loads, so reload
        # it after a change to show the new colour straight away.
        old_color = self.company_id.toolbar_color or False
        res = super().execute()
        if not res and (self.company_id.toolbar_color or False) != old_color:
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return res
