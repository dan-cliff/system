# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mrp_terminal_require_on_site = fields.Boolean(
        string='Only Workers On Site',
        help='Workers must be signed in at work (On Site) to sign in to a Work Centre app.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mrp_terminal_require_on_site = fields.Boolean(related='company_id.mrp_terminal_require_on_site', readonly=False)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    def _terminal_refusals(self, employees):
        refusals = super()._terminal_refusals(employees)
        if not self._terminal_company().mrp_terminal_require_on_site or not employees:
            return refusals
        now = fields.Datetime.now()
        on_site = set()
        for attendance in self.env['advanced.attendance'].sudo().search(
                [('employee_id', 'in', employees.ids), ('check_out', '=', False)]):
            due = attendance._auto_sign_out_due()
            if not due or due > now:
                on_site.add(attendance.employee_id.id)
        for employee in employees:
            if employee.id not in on_site:
                refusals.setdefault(employee.id, []).append(
                    self.env._('Please sign in On Site (at the sign in kiosk) before starting work.'))
        return refusals
