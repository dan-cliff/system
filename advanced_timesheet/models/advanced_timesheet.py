# -*- coding: utf-8 -*-
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_is_zero

# How often timesheets are submitted. Code works out each period's dates from
# these values, so they stay a fixed selection (see CLAUDE.md > Choice fields).
PERIOD_TYPES = [
    ('weekly', 'Weekly'),
    ('fortnightly', 'Fortnightly'),
    ('monthly', 'Monthly'),
]
PERIOD_LENGTHS = {'weekly': 7, 'fortnightly': 14}
# Weekly and fortnightly periods count from this date unless Settings say otherwise.
DEFAULT_PERIOD_START = date(2024, 1, 1)  # a Monday


class AdvancedTimesheet(models.Model):
    _name = 'advanced.timesheet'
    _description = 'Timesheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, person_name, id desc'

    name = fields.Char(string='Timesheet', compute='_compute_name', store=True)
    user_id = fields.Many2one(
        'res.users', string='User', index=True, tracking=True,
        default=lambda self: self.env.user,
    )
    person_name = fields.Char(
        string='Name', compute='_compute_person_name', store=True,
        help='Whose timesheet this is: the employee\'s name when Employees is installed, '
             'otherwise the user\'s.',
    )
    date_start = fields.Date(
        string='From', required=True, index=True, tracking=True,
        default=fields.Date.context_today,
        help='On a new timesheet, pick any day: the timesheet covers the whole period '
             '(week, fortnight or month) containing it.',
    )
    date_end = fields.Date(string='To', required=True, index=True, readonly=True, tracking=True)
    period_type = fields.Selection(PERIOD_TYPES, string='Period', readonly=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved')],
        string='Status', default='draft', required=True, readonly=True, copy=False,
        tracking=True, index=True,
    )
    line_ids = fields.One2many('advanced.timesheet.line', 'sheet_id', string='Entries', copy=False)
    total_hours = fields.Float(string='Total Hours', compute='_compute_total_hours', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, tracking=True,
        default=lambda self: self.env.company,
    )
    submitted_date = fields.Datetime(string='Submitted On', readonly=True, copy=False)
    approver_user_id = fields.Many2one(
        'res.users', string='Approver', compute='_compute_approver_user_id', store=True,
        help='Who approves this timesheet: the employee\'s Manager.',
    )
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    approval_required = fields.Boolean(compute='_compute_approval_required')
    can_approve = fields.Boolean(compute='_compute_can_approve')

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @api.model
    def _get_period_type(self):
        value = self.env['ir.config_parameter'].sudo().get_param('advanced_timesheet.period_type')
        return value if value in dict(PERIOD_TYPES) else 'weekly'

    @api.model
    def _get_period_anchor(self):
        value = self.env['ir.config_parameter'].sudo().get_param('advanced_timesheet.period_start')
        try:
            return fields.Date.to_date(value) or DEFAULT_PERIOD_START
        except ValueError:
            return DEFAULT_PERIOD_START

    @api.model
    def _approval_required(self):
        """Whether submitted timesheets wait for approval (see advanced_timesheet_hr)."""
        return False

    # ------------------------------------------------------------------
    # Whose timesheet it is. Employees (advanced_timesheet_hr) extends these.
    # ------------------------------------------------------------------
    @api.model
    def _person_field_names(self):
        return ['user_id']

    @api.model
    def _person_domain_from_vals(self, vals):
        return [('user_id', '=', vals.get('user_id') or False)]

    def _person_vals(self):
        self.ensure_one()
        return {'user_id': self.user_id.id}

    @api.model
    def _default_person_vals(self):
        return {'user_id': self.env.uid}

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('user_id.name')
    def _compute_person_name(self):
        for sheet in self:
            sheet.person_name = sheet.user_id.name

    @api.depends('person_name', 'date_start', 'date_end')
    def _compute_name(self):
        for sheet in self:
            dates = ' – '.join(d.strftime('%d/%m/%Y') for d in (sheet.date_start, sheet.date_end) if d)
            sheet.name = ' '.join(part for part in (sheet.person_name, dates) if part) or _('New Timesheet')

    @api.depends('line_ids.unit_amount')
    def _compute_total_hours(self):
        for sheet in self:
            sheet.total_hours = sum(sheet.line_ids.mapped('unit_amount'))

    def _compute_approver_user_id(self):
        self.approver_user_id = False

    def _compute_approval_required(self):
        self.approval_required = self._approval_required()

    @api.depends('state', 'approver_user_id')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        for sheet in self:
            sheet.can_approve = (
                sheet.state == 'submitted' and sheet.approval_required and sheet._is_approver()
            )

    # ------------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------------
    @api.model
    def _period_bounds(self, day, person_domain):
        """The period containing ``day``, cut short where it would overlap
        another timesheet of the same person (e.g. after the period setting
        changed)."""
        period_type = self._get_period_type()
        if period_type == 'monthly':
            start = day.replace(day=1)
            end = start + relativedelta(months=1, days=-1)
        else:
            length = PERIOD_LENGTHS[period_type]
            anchor = self._get_period_anchor()
            start = anchor + timedelta(days=(day - anchor).days // length * length)
            end = start + timedelta(days=length - 1)
        others = self.sudo().search(person_domain + [('date_start', '<=', end), ('date_end', '>=', start)])
        for other in others:
            if other.date_start <= day <= other.date_end:
                raise UserError(_('%(person)s already has a timesheet for %(day)s: %(sheet)s.',
                                  person=other.person_name, day=day.strftime('%d/%m/%Y'), sheet=other.name))
            if other.date_end < day:
                start = max(start, other.date_end + timedelta(days=1))
            else:
                end = min(end, other.date_start - timedelta(days=1))
        return start, end, period_type

    @api.model
    def _get_or_create_for(self, day, person_vals):
        """The timesheet of the given person (``user_id`` / ``employee_id``)
        covering ``day``, created if there is none yet."""
        domain = self._person_domain_from_vals(person_vals)
        existing = self.sudo().search(domain + [('date_start', '<=', day), ('date_end', '>=', day)], limit=1)
        if existing:
            return self.browse(existing.id)
        return self.create(dict(person_vals, date_start=day))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not any(vals.get(f) for f in self._person_field_names()):
                vals.update(self._default_person_vals())
            day = fields.Date.to_date(vals.get('date_start')) or fields.Date.context_today(self)
            start, end, period_type = self._period_bounds(day, self._person_domain_from_vals(vals))
            vals.update(date_start=start, date_end=end, period_type=period_type)
        return super().create(vals_list)

    @api.constrains('date_start', 'date_end', 'user_id')
    def _check_dates(self):
        for sheet in self:
            if sheet.date_end < sheet.date_start:
                raise ValidationError(_('A timesheet cannot end before it starts.'))
            overlap = self.sudo().search_count(sheet._person_domain_from_vals(sheet._person_vals()) + [
                ('id', '!=', sheet.id),
                ('date_start', '<=', sheet.date_end),
                ('date_end', '>=', sheet.date_start),
            ])
            if overlap:
                raise ValidationError(_('%s already has a timesheet in this period.', sheet.person_name))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if any(sheet.state == 'approved' for sheet in self) and not self._is_admin():
            raise UserError(_('Approved timesheets can only be deleted by an Timesheets Administrator.'))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Timesheet'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def action_open_my_timesheet(self):
        """Menu "My Timesheet": the current period's timesheet of the logged-in user."""
        today = fields.Date.context_today(self)
        return self._get_or_create_for(today, self._default_person_vals())._action_open()

    def action_previous_period(self):
        self.ensure_one()
        return self._get_or_create_for(self.date_start - timedelta(days=1), self._person_vals())._action_open()

    def action_next_period(self):
        self.ensure_one()
        return self._get_or_create_for(self.date_end + timedelta(days=1), self._person_vals())._action_open()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _is_admin(self):
        return self.env.user.has_group('advanced_timesheet.group_timesheet_admin')

    def _is_approver(self):
        """Whether the current user may approve this timesheet: they need the
        Approve permission and must be its approver (the employee's Manager),
        unless they are an Timesheets Administrator."""
        self.ensure_one()
        if self._is_admin():
            return True
        return (self.env.user.has_group('advanced_timesheet.group_timesheet_approve')
                and self.approver_user_id == self.env.user)

    def action_submit(self):
        self.check_access('write')
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_('Only draft timesheets can be submitted.'))
        self.sudo().write({'state': 'submitted', 'submitted_date': fields.Datetime.now()})
        for sheet in self:
            if not sheet.approval_required:
                sheet.message_post(body=_('Timesheet submitted.'))
            elif sheet.approver_user_id:
                sheet.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=sheet.approver_user_id.id,
                    summary=_('Approve timesheet'),
                    note=_('%s submitted their timesheet for approval.', sheet.person_name),
                )
                sheet.message_post(body=_('Timesheet submitted for approval by %s.', sheet.approver_user_id.name))
            else:
                sheet.message_post(body=_(
                    'Timesheet submitted for approval. No Manager is set for this employee, '
                    'so an Timesheets Administrator must approve it.'))
        return True

    def action_approve(self):
        for sheet in self:
            if sheet.state != 'submitted' or not sheet.approval_required:
                raise UserError(_('Only timesheets waiting for approval can be approved.'))
            if not sheet._is_approver():
                raise AccessError(_('Only the employee\'s Manager can approve %s.', sheet.name))
        self.sudo().write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })
        for sheet in self:
            sheet.sudo().activity_feedback(['mail.mail_activity_data_todo'], feedback=_('Approved'))
            sheet.message_post(body=_('Timesheet approved.'))
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state != 'submitted' or not self._is_approver():
            raise AccessError(_('Only the employee\'s Manager can send %s back.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Back'),
            'res_model': 'advanced.timesheet.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_timesheet_id': self.id},
        }

    def _do_reject(self, reason):
        for sheet in self:
            if sheet.state != 'submitted' or not sheet._is_approver():
                raise AccessError(_('Only the employee\'s Manager can send %s back.', sheet.name))
        self.sudo().write({'state': 'draft', 'submitted_date': False})
        for sheet in self:
            sheet.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            sheet.message_post(body=_('Timesheet sent back for changes: %s', reason))
            if sheet.user_id:
                sheet.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=sheet.user_id.id,
                    summary=_('Correct and resubmit timesheet'),
                    note=reason,
                )

    def action_reset_to_draft(self):
        self.check_access('write')
        for sheet in self:
            if sheet.state == 'draft':
                continue
            if sheet.state == 'approved' and not self._is_admin():
                raise UserError(_('Only an Timesheets Administrator can reopen an approved timesheet.'))
        sheets = self.filtered(lambda s: s.state != 'draft')
        sheets.sudo().write({'state': 'draft', 'submitted_date': False, 'approved_by_id': False, 'approved_date': False})
        for sheet in sheets:
            sheet.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            sheet.message_post(body=_('Timesheet reset to draft.'))
        return True

    # ------------------------------------------------------------------
    # Grid (static/src/timesheet_grid)
    # ------------------------------------------------------------------
    def _grid_days(self):
        self.ensure_one()
        return [self.date_start + timedelta(days=n) for n in range((self.date_end - self.date_start).days + 1)]

    def get_grid_data(self):
        """Rows (project / task, plus automatic rows such as attendances),
        the period's days grouped into weeks, and the hours per cell."""
        self.ensure_one()
        days = self._grid_days()
        week_start = self._get_period_anchor().weekday()
        weeks = []
        for day in days:
            if not weeks or day.weekday() == week_start:
                weeks.append({'start': fields.Date.to_string(day), 'days': []})
            weeks[-1]['days'].append(fields.Date.to_string(day))

        rows = {}
        for line in self.line_ids.sorted(lambda l: (l.is_auto, l.project_id.display_name or '',
                                                    l.task_id.display_name or '', l.id)):
            key = line._grid_row_key()
            row = rows.get(key)
            if row is None:
                row = rows[key] = {
                    'key': '%s-%s-%s' % key,
                    'project_id': line.project_id.id,
                    'task_id': line.task_id.id,
                    'is_auto': line.is_auto,
                    'project': line.project_id.display_name or (line._grid_auto_label() if line.is_auto else _('No Project')),
                    'task': line.task_id.display_name or '',
                    'cells': {},
                    'total': 0.0,
                }
            day = fields.Date.to_string(line.date)
            row['cells'][day] = row['cells'].get(day, 0.0) + line.unit_amount
            row['total'] += line.unit_amount

        return {
            'days': [fields.Date.to_string(day) for day in days],
            'weeks': weeks,
            'rows': list(rows.values()),
            'today': fields.Date.to_string(fields.Date.context_today(self)),
            'editable': self.state == 'draft' and self.has_access('write'),
            'state': self.state,
        }

    def set_grid_cell(self, row, day, hours):
        """Set the hours of a grid cell: the row's manual entries on that day
        are adjusted (or one is created) so they add up to ``hours``."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Submitted timesheets cannot be changed. Reset it to draft first.'))
        if row.get('is_auto'):
            raise UserError(_('Hours filled in automatically cannot be changed here.'))
        day = fields.Date.to_date(day)
        if not self.date_start <= day <= self.date_end:
            raise UserError(_('%s is outside this timesheet\'s period.', day.strftime('%d/%m/%Y')))
        hours = max(float(hours or 0.0), 0.0)
        Line = self.env['advanced.timesheet.line']
        lines = self.line_ids.filtered(
            lambda l: not l.is_auto
            and l.project_id.id == (row.get('project_id') or False)
            and l.task_id.id == (row.get('task_id') or False)
        ).sorted('id')
        day_lines = lines.filtered(lambda l: l.date == day)
        if float_is_zero(hours - sum(day_lines.mapped('unit_amount')), precision_digits=2):
            return True
        if float_is_zero(hours, precision_digits=2):
            # Keep one empty entry when it is all that holds the row on the grid.
            keep = day_lines[:1] if lines == day_lines else Line
            (day_lines - keep).unlink()
            keep.write({'unit_amount': 0.0})
        elif day_lines:
            rest = sum(day_lines[:-1].mapped('unit_amount'))
            if hours >= rest:
                day_lines[-1].write({'unit_amount': hours - rest})
            else:
                day_lines[1:].unlink()
                day_lines[0].write({'unit_amount': hours})
        elif lines and all(float_is_zero(l.unit_amount, precision_digits=2) for l in lines):
            # The row only has its empty placeholder entry: use it.
            lines[0].write({'date': day, 'unit_amount': hours})
        else:
            Line.create({
                'sheet_id': self.id,
                'date': day,
                'project_id': row.get('project_id') or False,
                'task_id': row.get('task_id') or False,
                'name': lines[-1:].name or False,
                'unit_amount': hours,
            })
        return True
