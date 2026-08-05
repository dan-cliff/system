from odoo import fields, models


class InjuryConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    injury_integrate_rtw = fields.Boolean(
        string='Integrate Incident and Return to Work',
        config_parameter='injury_management.integrate_rtw',
        help='When enabled, automatically creates a Return to Work case when an '
             'incident report is saved with a Lost Time Injury or Restricted / '
             'Modified Duties flag set.')

    # Computed flags used to make the toggle read-only when either module is absent
    incident_management_installed = fields.Boolean(
        compute='_compute_modules_installed')
    injury_management_installed = fields.Boolean(
        compute='_compute_modules_installed')

    def _compute_modules_installed(self):
        IrModule = self.env['ir.module.module']
        inc_ok = bool(IrModule.search(
            [('name', '=', 'incident_management'), ('state', '=', 'installed')], limit=1))
        rtw_ok = bool(IrModule.search(
            [('name', '=', 'injury_management'), ('state', '=', 'installed')], limit=1))
        for rec in self:
            rec.incident_management_installed = inc_ok
            rec.injury_management_installed = rtw_ok
