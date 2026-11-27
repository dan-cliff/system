from odoo import _, models
from odoo.exceptions import AccessError
from odoo.fields import Domain


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_pos_insights_user(self, employee_id=False):
        self.ensure_one()
        config = self.config_id
        if not config.module_pos_hr:
            return super()._get_pos_insights_user(employee_id)
        if not employee_id:
            raise AccessError(_("Log in as a cashier to print session reports."))
        # Only an employee who can log in to this POS counts (the same
        # employees the POS loads), and their linked user decides access.
        employee = self.env['hr.employee'].sudo().search(
            Domain(config._employee_domain(config.current_user_id.id)) & Domain('id', '=', int(employee_id)),
            limit=1,
        )
        if not employee:
            raise AccessError(_("This employee can't log in to this Point of Sale."))
        return employee.user_id
