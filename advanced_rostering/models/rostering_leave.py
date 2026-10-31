# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .rostering_tools import search_positive

# Fields of the request itself: once submitted they only change through the
# workflow (reset to draft first).
REQUEST_FIELDS = {'user_id', 'leave_type_id', 'date_from', 'date_to', 'reason', 'request_unit',
                  'datetime_from', 'datetime_to'}
# Hours of a whole day off when Personnel has no working hours to go by.
DEFAULT_FULL_DAY_HOURS = 7.6


class RosteringLeave(models.Model):
    _name = 'rostering.leave'
    _description = 'Leave Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'
    # Publishers and approvers post on records they can read but not edit.
    _mail_post_access = 'read'

    name = fields.Char(string='Leave Request', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', string='User', index=True, tracking=True,
                              default=lambda self: self.env.user)
    person_name = fields.Char(string='Person', compute='_compute_person_name', store=True)
    leave_type_id = fields.Many2one('rostering.leave.type', string='Leave Type', required=True, tracking=True,
                                    index=True, ondelete='restrict',
                                    domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    date_from = fields.Date(string='From', required=True, index=True, tracking=True,
                            default=fields.Date.context_today)
    date_to = fields.Date(string='To', required=True, index=True, tracking=True,
                          default=fields.Date.context_today)
    # Whole days or part of one day; the code works out hours from it, so it stays a fixed selection.
    request_unit = fields.Selection(
        [('day', 'Whole Days'), ('partial', 'Part of a Day')], string='Leave For', required=True,
        default='day', tracking=True,
    )
    datetime_from = fields.Datetime(string='From (Time)', tracking=True, copy=False,
                                    help='Start of a part-day leave.')
    datetime_to = fields.Datetime(string='To (Time)', tracking=True, copy=False,
                                  help='End of a part-day leave, on the same day.')
    duration_days = fields.Float(
        string='Days', digits=(16, 2), compute='_compute_hours', store=True,
        help='Days of leave, leaving out public holidays (a part day counts as its share of a full day).',
    )
    hours = fields.Float(
        string='Hours', compute='_compute_hours', store=True,
        help='Hours off: whole days × the full-time hours of a day, or the time between From and To for '
             'a part day. Public holidays are left out.',
    )
    public_holiday_ids = fields.Many2many(
        'rostering.public.holiday', string='Public Holidays', compute='_compute_hours',
        help='Public holidays of the person during the leave: not counted as leave.',
    )
    holiday_days = fields.Float(string='Public Holiday Days', digits=(16, 2), compute='_compute_hours')
    holiday_hours = fields.Float(string='Public Holiday Hours', compute='_compute_hours')
    reason = fields.Text(string='Reason')
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'To Approve'), ('approved', 'Approved'),
         ('refused', 'Refused'), ('cancelled', 'Cancelled')],
        string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True, index=True,
    )
    approver_user_id = fields.Many2one(
        'res.users', string='Approver', compute='_compute_approver_user_id', store=True, index=True,
        help='Who approves the request: the employee\'s Manager (with Personnel). Without one, '
             'the request waits in the To Approve queue for the Leave Requests: Approve team.',
    )
    submitted_date = fields.Datetime(string='Submitted On', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    refused_by_id = fields.Many2one('res.users', string='Refused By', readonly=True, copy=False)
    refuse_reason = fields.Text(string='Refusal Reason', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, tracking=True,
                                 default=lambda self: self.env.company)
    can_approve = fields.Boolean(string='I Can Approve', compute='_compute_can_approve',
                                 search='_search_can_approve')
    is_mine = fields.Boolean(string='My Requests', compute='_compute_is_mine', search='_search_is_mine')
    shift_ids = fields.Many2many('rostering.shift', string='Rostered Shifts', compute='_compute_shift_ids',
                                 help='Published shifts of the person during the leave.')
    shift_count = fields.Integer(string='Rostered Shifts Count', compute='_compute_shift_ids')

    # ------------------------------------------------------------------
    # Whose request it is. Personnel (advanced_rostering_hr) extends these.
    # ------------------------------------------------------------------
    @api.model
    def _person_field(self):
        return 'user_id'

    @api.model
    def _my_domain(self):
        return [('user_id', '=', self.env.uid)]

    def _person_users(self):
        """Users the request is for (to notify them)."""
        return self.user_id

    def _may_request_for(self):
        """Whether the current user may request this leave: their own, or
        anyone's with Create and Edit All (Personnel adds My Team)."""
        self.ensure_one()
        return (self.filtered_domain(self._my_domain())
                or self.env.user.has_group('advanced_rostering.group_leave_edit_all'))

    @api.depends('user_id.name')
    def _compute_person_name(self):
        for leave in self:
            leave.person_name = leave.user_id.name

    def _compute_approver_user_id(self):
        self.approver_user_id = False

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('person_name', 'leave_type_id.name', 'date_from', 'date_to')
    def _compute_name(self):
        for leave in self:
            days = [d for d in (leave.date_from, leave.date_to) if d]
            dates = ' – '.join(dict.fromkeys(d.strftime('%d/%m/%Y') for d in days))
            parts = [leave.person_name, leave.leave_type_id.name, dates]
            leave.name = ' · '.join(part for part in parts if part) or _('New Leave Request')

    # ------------------------------------------------------------------
    # Hours, days and public holidays
    # ------------------------------------------------------------------
    def _get_tz(self):
        self.ensure_one()
        return self.user_id.tz or self.env.user.tz or 'UTC'

    def _full_day_hours(self):
        """Hours of a whole day off (Personnel uses the company's working hours)."""
        try:
            return float(self.env['ir.config_parameter'].sudo().get_param(
                'advanced_rostering.leave_hours_per_day', DEFAULT_FULL_DAY_HOURS))
        except ValueError:
            return DEFAULT_FULL_DAY_HOURS

    def _holiday_jurisdictions(self):
        """Public holiday jurisdictions of the person (Personnel can use the employee's own)."""
        self.ensure_one()
        return self.env['rostering.holiday.jurisdiction']._for_company(self.company_id or self.env.company)

    def _local_date(self, value):
        self.ensure_one()
        return pytz.utc.localize(value).astimezone(pytz.timezone(self._get_tz())).date()

    def _local_datetime(self, day, hours):
        """Naive UTC datetime of ``hours`` after midnight of ``day`` in the person's time zone."""
        self.ensure_one()
        local = datetime.combine(day, time()) + timedelta(hours=hours)
        return pytz.timezone(self._get_tz()).localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def _partial_hours(self):
        self.ensure_one()
        if not (self.datetime_from and self.datetime_to) or self.datetime_to <= self.datetime_from:
            return 0.0
        return (self.datetime_to - self.datetime_from).total_seconds() / 3600

    def _days(self):
        self.ensure_one()
        if not (self.date_from and self.date_to) or self.date_to < self.date_from:
            return []
        return [self.date_from + timedelta(days=n) for n in range((self.date_to - self.date_from).days + 1)]

    def _public_holidays(self):
        self.ensure_one()
        if not (self.date_from and self.date_to):
            return self.env['rostering.public.holiday']
        return self.env['rostering.public.holiday']._in_range(self.date_from, self.date_to)._applying_to(
            self._holiday_jurisdictions(), self.company_id)

    def _hours_by_day(self):
        """Hours off on each day of the leave, public holidays left out."""
        self.ensure_one()
        holiday_dates = set(self._public_holidays().mapped('date'))
        if self.request_unit == 'partial':
            hours = self._partial_hours()
            return {self.date_from: hours} if hours and self.date_from not in holiday_dates else {}
        per_day = self._full_day_hours()
        return {day: per_day for day in self._days() if day not in holiday_dates}

    @api.depends('request_unit', 'date_from', 'date_to', 'datetime_from', 'datetime_to', 'user_id', 'company_id')
    def _compute_hours(self):
        for leave in self:
            holidays = leave._public_holidays()
            holiday_dates = set(holidays.mapped('date'))
            per_day = leave._full_day_hours()
            by_day = leave._hours_by_day()
            leave.public_holiday_ids = holidays
            leave.hours = sum(by_day.values())
            if leave.request_unit == 'partial':
                on_holiday = leave.date_from in holiday_dates
                leave.duration_days = leave.hours / per_day if per_day else 0.0
                leave.holiday_days = 1.0 if on_holiday and leave._partial_hours() else 0.0
                leave.holiday_hours = leave._partial_hours() if on_holiday else 0.0
            else:
                leave.duration_days = len(by_day)
                leave.holiday_days = len([day for day in leave._days() if day in holiday_dates])
                leave.holiday_hours = leave.holiday_days * per_day

    @api.onchange('request_unit')
    def _onchange_request_unit(self):
        if self.request_unit == 'partial' and self.date_from and not self.datetime_from:
            self.datetime_from = self._local_datetime(self.date_from, 9.0)
            self.datetime_to = self._local_datetime(self.date_from, 13.0)

    @api.onchange('datetime_from', 'datetime_to')
    def _onchange_datetimes(self):
        if self.request_unit == 'partial' and self.datetime_from:
            self.date_from = self.date_to = self._local_date(self.datetime_from)

    def _covers_shift(self, shift):
        """Whether the leave takes the person off ``shift``: a whole day does;
        a part day when its times overlap the shift's."""
        self.ensure_one()
        if self.request_unit != 'partial':
            return True
        if not (self.datetime_from and self.datetime_to and shift.start_datetime and shift.end_datetime):
            return True
        return self.datetime_from < shift.end_datetime and self.datetime_to > shift.start_datetime

    def _sync_partial_dates(self):
        """A part-day leave covers the day of its start time."""
        for leave in self.filtered(lambda l: l.request_unit == 'partial' and l.datetime_from):
            day = leave._local_date(leave.datetime_from)
            if leave.date_from != day or leave.date_to != day:
                super(RosteringLeave, leave).write({'date_from': day, 'date_to': day})

    @api.depends('state', 'approver_user_id', 'user_id')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        for leave in self:
            leave.can_approve = leave._is_approver()

    def _search_can_approve(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = [('state', '=', 'submitted')]
        if not self._is_admin():
            domain += [('user_id', '!=', self.env.uid)]
            if not self._is_queue_approver():
                domain += [('approver_user_id', '=', self.env.uid)]
        if positive:
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self.filtered_domain(self._my_domain())
        for leave in self:
            leave.is_mine = leave in mine

    def _search_is_mine(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = self._my_domain()
        if positive:
            return domain
        return [('id', 'not in', self.search(domain).ids)]

    @api.depends('date_from', 'date_to', 'user_id')
    def _compute_shift_ids(self):
        field = self._person_field()
        Shift = self.env['rostering.shift']
        for leave in self:
            shifts = Shift
            if leave[field] and leave.date_from and leave.date_to:
                shifts = Shift.sudo().search([
                    (field, '=', leave[field].id),
                    ('roster_state', '=', 'published'),
                    ('date', '>=', leave.date_from),
                    ('date', '<=', leave.date_to),
                ])
            leave.shift_ids = shifts
            leave.shift_count = len(shifts)

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to', 'request_unit', 'datetime_from', 'datetime_to')
    def _check_dates(self):
        for leave in self:
            if leave.date_to < leave.date_from:
                raise ValidationError(_('Leave cannot end before it starts.'))
            if leave.request_unit != 'partial':
                continue
            if not (leave.datetime_from and leave.datetime_to):
                raise ValidationError(_('A part-day leave needs its From and To times.'))
            if leave.datetime_to <= leave.datetime_from:
                raise ValidationError(_('A part-day leave must end after it starts.'))
            if leave._local_date(leave.datetime_from) != leave._local_date(leave.datetime_to):
                raise ValidationError(_('A part-day leave must start and end on the same day. '
                                        'Use Whole Days for leave over several days.'))

    @api.constrains('date_from', 'date_to', 'state', 'user_id', 'datetime_from', 'datetime_to')
    def _check_overlap(self):
        field = self._person_field()
        for leave in self.filtered(lambda l: l.state in ('draft', 'submitted', 'approved') and l[field]):
            other = self.sudo().search([
                ('id', '!=', leave.id),
                (field, '=', leave[field].id),
                ('state', 'in', ('draft', 'submitted', 'approved')),
                ('date_from', '<=', leave.date_to),
                ('date_to', '>=', leave.date_from),
            ])
            if leave.request_unit == 'partial':
                # Two part days on the same day only clash when their times overlap.
                other = other.filtered(lambda o: o.request_unit != 'partial' or (
                    o.datetime_from and o.datetime_to
                    and o.datetime_from < leave.datetime_to and o.datetime_to > leave.datetime_from))
            other = other[:1]
            if other:
                raise ValidationError(_('%(person)s already has leave from %(start)s to %(end)s (%(request)s).',
                                        person=leave.person_name,
                                        start=other.date_from.strftime('%d/%m/%Y'),
                                        end=other.date_to.strftime('%d/%m/%Y'),
                                        request=other.leave_type_id.name))

    def _check_request_for(self):
        if self.env.su:
            return
        for leave in self:
            if not leave._may_request_for():
                raise AccessError(_('You can only request leave for yourself%s.',
                                    _(' and your team') if self._fields.get('employee_id') else ''))

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._sync_partial_dates()
        leaves._check_request_for()
        for leave in leaves:
            users = leave._person_users()
            if users:
                leave.sudo().message_subscribe(partner_ids=users.partner_id.ids)
        return leaves

    def write(self, vals):
        if not self.env.su and REQUEST_FIELDS.union(self._person_fields()) & set(vals):
            if any(leave.state != 'draft' for leave in self) and not self._is_admin():
                raise UserError(_('Only draft leave requests can be changed. Cancel or reset it to draft first.'))
        res = super().write(vals)
        if {'request_unit', 'datetime_from', 'datetime_to'} & set(vals):
            self._sync_partial_dates()
        if set(self._person_fields()) & set(vals):
            self._check_request_for()
        return res

    @api.model
    def _person_fields(self):
        return ['user_id']

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self):
        if any(leave.state in ('submitted', 'approved') for leave in self) and not self._is_admin():
            raise UserError(_('Cancel a submitted or approved leave request before deleting it.'))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _is_admin(self):
        return self.env.user.has_group('advanced_rostering.group_rostering_admin')

    def _is_queue_approver(self):
        return self.env.user.has_group('advanced_rostering.group_leave_approve')

    def _is_approver(self):
        """Whether the current user may approve or refuse this request: the
        approver (the employee's Manager), anyone in the Leave Requests:
        Approve team, or a Rostering Administrator. Nobody but an
        Administrator approves their own leave."""
        self.ensure_one()
        if self.state != 'submitted':
            return False
        if self._is_admin():
            return True
        if self.filtered_domain(self._my_domain()):
            return False
        return self._is_queue_approver() or self.approver_user_id == self.env.user

    def _check_requester(self):
        """The person, or whoever may request leave for them, drives the
        request (Create Only users included: they submit what they created)."""
        self.check_access('read')
        if self.env.su:
            return
        for leave in self:
            if not leave._may_request_for():
                raise AccessError(_('Only %s or their manager can do this.', leave.person_name))

    def action_submit(self):
        self._check_requester()
        for leave in self:
            if leave.state != 'draft':
                raise UserError(_('Only draft leave requests can be submitted.'))
        self.sudo().write({'state': 'submitted', 'submitted_date': fields.Datetime.now()})
        for leave in self:
            if leave.approver_user_id:
                leave.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=leave.approver_user_id.id,
                    summary=_('Approve leave request'),
                    note=_('%(person)s requested %(type)s from %(start)s to %(end)s.',
                           person=leave.person_name, type=leave.leave_type_id.name,
                           start=leave.date_from.strftime('%d/%m/%Y'), end=leave.date_to.strftime('%d/%m/%Y')),
                )
                leave.message_post(body=_('Leave request submitted for approval by %s.',
                                          leave.approver_user_id.name))
            else:
                leave.message_post(body=_('Leave request submitted. It is waiting in Leave Requests › '
                                          'To Approve for the leave approvers.'))
        return True

    def _check_approver(self):
        for leave in self:
            if not leave._is_approver():
                raise AccessError(_('You cannot approve or refuse %s.', leave.name))

    def action_approve(self):
        self._check_approver()
        self.sudo().write({'state': 'approved', 'approved_by_id': self.env.uid,
                           'approved_date': fields.Datetime.now()})
        for leave in self:
            leave.sudo().activity_feedback(['mail.mail_activity_data_todo'], feedback=_('Approved'))
            leave.message_post(body=_('Leave request approved.'), partner_ids=leave._person_users().partner_id.ids)
            if leave.shift_count:
                leave.message_post(body=Markup('<p>%s</p>') % _(
                    '%s published shift(s) fall during this leave and need covering.', leave.shift_count))
        return True

    def action_open_refuse_wizard(self):
        self.ensure_one()
        self._check_approver()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Leave Request'),
            'res_model': 'rostering.leave.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_leave_id': self.id},
        }

    def _do_refuse(self, reason):
        self._check_approver()
        self.sudo().write({'state': 'refused', 'refused_by_id': self.env.uid, 'refuse_reason': reason})
        for leave in self:
            leave.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            leave.message_post(body=_('Leave request refused: %s', reason),
                               partner_ids=leave._person_users().partner_id.ids)

    def action_cancel(self):
        """The person (or whoever requested it) cancels a draft or waiting
        request; approved leave is cancelled by an approver."""
        for leave in self:
            if leave.state in ('refused', 'cancelled'):
                continue
            if leave.state == 'approved':
                if not (self._is_admin() or self._is_queue_approver()
                        or leave.approver_user_id == self.env.user):
                    raise AccessError(_('Approved leave can only be cancelled by an approver. '
                                        'Ask your manager to cancel it.'))
            else:
                leave._check_requester()
        leaves = self.filtered(lambda l: l.state not in ('refused', 'cancelled'))
        leaves.sudo().write({'state': 'cancelled'})
        for leave in leaves:
            leave.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            leave.message_post(body=_('Leave request cancelled.'))
        return True

    def action_reset_to_draft(self):
        self.check_access('write')
        for leave in self:
            if leave.state not in ('refused', 'cancelled', 'submitted'):
                raise UserError(_('Only waiting, refused or cancelled requests can be reset to draft.'))
        self.sudo().write({'state': 'draft', 'submitted_date': False, 'refused_by_id': False,
                           'refuse_reason': False})
        for leave in self:
            leave.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            leave.message_post(body=_('Leave request reset to draft.'))
        return True

    def action_view_shifts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_rostering.action_rostering_shift')
        action.update({
            'name': _('Rostered Shifts'),
            'domain': [('id', 'in', self.shift_ids.ids)],
            'context': {},
        })
        return action
