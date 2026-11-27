# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .hr_version import _NEW_EMPLOYEE_VERSION


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['advanced.hr.audit.mixin', 'hr.employee']

    # Fields only on hr.employee need an HR group (see hr's hr.employee.public).
    personnel_initials = fields.Char(compute='_compute_personnel_initials', groups='hr.group_hr_user')
    personnel_audit_count = fields.Integer(
        string='Audit Trail', compute='_compute_personnel_audit_count',
        groups='advanced_hr.group_audit_trail_view')

    @api.depends('name')
    def _compute_personnel_initials(self):
        for employee in self:
            words = (employee.name or '').split()
            employee.personnel_initials = ''.join(word[0] for word in words[:1] + words[1:][-1:]).upper() or '?'

    def _compute_personnel_audit_count(self):
        counts = dict(self.env['advanced.hr.audit.trail']._read_group(
            [('res_model', '=', 'hr.employee'), ('res_id', 'in', self.ids)],
            ['res_id'], ['__count'],
        )) if self.ids else {}
        for employee in self:
            employee.personnel_audit_count = counts.get(employee.id, 0)

    @api.model
    def _create(self, data_list):
        # The new employees are checked by the create rules; their versions
        # get the employee's details as part of creating them (see hr.version).
        employees = super(HrEmployee, self.with_context(
            personnel_new_employee_version=_NEW_EMPLOYEE_VERSION))._create(data_list)
        return employees.with_env(self.env)

    # ── Public profiles of the employees outside a user's permissions ─────
    #
    # Personnel's Employees permissions include Odoo's HR Officer group (Odoo
    # needs it to manage employees) and their record rules decide which
    # employees a user may find and open. Reading an employee they may not
    # open (a colleague shown in another app, a manager, ...) reads its public
    # profile (hr.employee.public) instead of failing, as it does for users
    # without HR rights; private details still raise an access error.

    def _personnel_public_fallback(self):
        return not self.env.su and self.env.user.has_group('advanced_hr.group_personnel_user')

    def _personnel_denied(self):
        return self - self._filtered_access('read')

    def _personnel_fetch_public(self, field_names):
        """Fill the cache with the public data of ``self`` (see hr's fetch)."""
        public_fields = self.env['hr.employee.public']._fields
        field_names = [name for name in field_names if name in public_fields and name != 'current_version_id']
        public = self.env['hr.employee.public'].browse(self._ids)
        public.fetch(field_names)
        for name in field_names:
            public_field = public_fields[name]
            private_field = self._fields[name]
            if (public_field.related and public_field.related_field.model_name == 'hr.employee'
                    or private_field.inherited and private_field.inherited_field.model_name == 'hr.version'):
                public.mapped(name)
        self._copy_cache_from(public, field_names)

    def _fetch_field(self, field):
        if self._personnel_public_fallback() and field.name in self.env['hr.employee.public']._fields:
            denied = self._personnel_denied()
            if denied:
                allowed = self - denied
                if allowed:
                    super(HrEmployee, allowed)._fetch_field(field)
                denied._personnel_fetch_public([field.name])
                return
        return super()._fetch_field(field)

    def _compute_field_value(self, field):
        # Version fields (department, job, ...) are computed from the version,
        # which follows the same permissions: read them from the public profile.
        if (field.inherited and field.inherited_field.model_name == 'hr.version'
                and field.name in self.env['hr.employee.public']._fields
                and self._personnel_public_fallback()):
            denied = self._personnel_denied()
            if denied:
                allowed = self - denied
                if allowed:
                    super(HrEmployee, allowed)._compute_field_value(field)
                denied._personnel_fetch_public([field.name])
                return
        return super()._compute_field_value(field)

    def fetch(self, field_names=None):
        if self and field_names and self._personnel_public_fallback():
            public_fields = self.env['hr.employee.public']._fields
            if all(name in public_fields for name in field_names):
                denied = self._personnel_denied()
                if denied:
                    allowed = self - denied
                    if allowed:
                        super(HrEmployee, allowed).fetch(field_names)
                    denied._personnel_fetch_public(field_names)
                    return
        return super().fetch(field_names)

    def get_formview_id(self, access_uid=None):
        if self and not access_uid and self._personnel_public_fallback() and self._personnel_denied():
            return self.env.ref('hr.hr_employee_public_view_form').id
        return super().get_formview_id(access_uid=access_uid)

    def get_formview_action(self, access_uid=None):
        res = super().get_formview_action(access_uid=access_uid)
        if self and not access_uid and self._personnel_public_fallback() and self._personnel_denied():
            res['res_model'] = 'hr.employee.public'
        return res

    # ── ID Badges ─────────────────────────────────────────────────────────

    def _personnel_badge_templates(self):
        """The badge templates offered to all of these employees."""
        Template = self.env['advanced.hr.badge.template']
        templates = Template.search([])
        companies = self.company_id
        return templates.filtered(lambda t: not t.company_id or (companies and companies <= t.company_id))

    def action_print_personnel_badge(self):
        templates = self._personnel_badge_templates()
        if not templates:
            raise UserError(self.env._(
                "There is no ID badge for %(employees)s. Design one in Personnel › Configuration › ID Badges, "
                "with no company or with the employees' company.",
                employees=', '.join(self.mapped('name')),
            ))
        return templates[0].report_action_id.report_action(self, config=False)
