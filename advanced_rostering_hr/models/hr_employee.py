# -*- coding: utf-8 -*-
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Rostering's Employee fields list every employee's public profile.

        Personnel's record rules limit searching hr.employee to the employees
        a user's Employees permissions cover (possibly none), while rosters
        and leave requests are made for anyone. The names come from
        hr.employee.public, which every internal user may search anyway;
        Personnel reads the chosen employee's public profile the same way.
        """
        if self.env.context.get('rostering_employee_picker') and not self.env.su:
            public = self.env['hr.employee.public'].with_context(rostering_employee_picker=False)
            return public.name_search(name, domain, operator, limit)
        return super().name_search(name, domain, operator, limit)
