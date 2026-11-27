# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

    # ── Public holiday jurisdictions (Settings › Rostering) ─────────────
    rostering_holiday_jurisdiction_ids = fields.Many2many(
        'rostering.holiday.jurisdiction', 'hr_employee_rostering_holiday_jurisdiction_rel', 'employee_id',
        'jurisdiction_id', string='Public Holiday Jurisdictions',
        compute='_compute_rostering_holiday_jurisdiction_ids', store=True, readonly=False,
        groups='hr.group_hr_user',
        help='Which public holidays apply to the employee in Rostering. The Country and State of their '
             'Work Address are picked automatically; add religions or others by hand.',
    )
    # Fields only on hr.employee need an HR group (see hr's hr.employee.public).
    rostering_jurisdictions_enabled = fields.Boolean(compute='_compute_rostering_jurisdictions_enabled',
                                                     groups='hr.group_hr_user')

    @api.model
    def _rostering_jurisdictions_switched_on(self):
        params = self.env['ir.config_parameter'].sudo()
        return (params.get_param('advanced_rostering.holiday_import') == 'True'
                and params.get_param('advanced_rostering.employee_jurisdictions') == 'True')

    def _compute_rostering_jurisdictions_enabled(self):
        self.rostering_jurisdictions_enabled = self._rostering_jurisdictions_switched_on()

    @api.depends('address_id', 'address_id.country_id', 'address_id.state_id')
    def _compute_rostering_holiday_jurisdiction_ids(self):
        if not self._rostering_jurisdictions_switched_on():
            for employee in self:
                employee.rostering_holiday_jurisdiction_ids = employee.rostering_holiday_jurisdiction_ids
            return
        for employee in self:
            employee.rostering_holiday_jurisdiction_ids = employee._rostering_address_jurisdictions()

    def _rostering_address_jurisdictions(self):
        """The jurisdictions picked by hand (religion, other) plus the Country
        and State jurisdictions of the Work Address."""
        self.ensure_one()
        kept = self.rostering_holiday_jurisdiction_ids.filtered(lambda j: j.kind not in ('country', 'state'))
        address = self.env['rostering.holiday.jurisdiction']._for_address(
            self.address_id.country_id, self.address_id.state_id)
        return kept | address

    @api.model
    def _rostering_apply_address_jurisdictions(self):
        """Fill every employee's jurisdictions from their address (when the
        switch is turned on, and after an import adds jurisdictions)."""
        if not self._rostering_jurisdictions_switched_on():
            return
        employees = self.sudo().with_context(active_test=False).search([])
        for employee in employees:
            jurisdictions = employee._rostering_address_jurisdictions()
            if jurisdictions != employee.rostering_holiday_jurisdiction_ids:
                employee.rostering_holiday_jurisdiction_ids = jurisdictions
