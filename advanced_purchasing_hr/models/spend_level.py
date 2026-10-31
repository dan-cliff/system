# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchasingSpendLevel(models.Model):
    _inherit = 'advanced.purchasing.spend.level'

    employee_ids = fields.One2many('hr.employee', 'purchase_spend_level_id', string='Employees',
                                   groups='hr.group_hr_user')
    employee_count = fields.Integer('Employee Count', compute='_compute_employee_count')

    def _compute_employee_count(self):
        counts = dict(self.env['hr.employee'].sudo()._read_group(
            [('purchase_spend_level_id', 'in', self.ids)], ['purchase_spend_level_id'], ['__count']))
        for level in self:
            level.employee_count = counts.get(level, 0)

    def action_open_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Employees with %s', self.name),
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('purchase_spend_level_id', '=', self.id)],
        }
