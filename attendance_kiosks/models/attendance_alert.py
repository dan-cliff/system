import logging
from datetime import datetime, time, timedelta

import pytz
from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

ALERT_EVENTS = [
    ('in_first_today', 'First sign in today'),
    ('in_first_site', 'First ever sign in at the site'),
    ('in_first_site_today', 'First sign in at the site today'),
    ('in_every', 'Every sign in'),
    ('out_first_today', 'First sign out today'),
    ('out_first_site_today', 'First sign out from the site today'),
    ('out_every', 'Every sign out'),
]
WEEKDAY_FIELDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


class AttendanceAlert(models.Model):
    _name = 'attendance.alert'
    _description = 'Attendance Sign In / Out Alert'
    _inherit = ['mail.thread']
    _order = 'active desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, tracking=True, default=lambda self: self.env.company,
    )
    requester_id = fields.Many2one(
        'res.users', string='Requested By', required=True, tracking=True,
        default=lambda self: self.env.user, domain="[('share', '=', False)]",
        help='This user is sent a Discuss message when the alert runs.',
    )

    # ── Who ────────────────────────────────────────────────────────────────
    all_employees = fields.Boolean(
        string='Everyone in the Company',
        help='Watch every employee of the company, e.g. to post all arrivals and departures to a channel.',
    )
    employee_ids = fields.Many2many(
        'hr.employee', 'attendance_alert_employee_rel', 'alert_id', 'employee_id',
        string='Employees', check_company=True, domain="[('company_id', '=', company_id)]",
    )

    # ── When ───────────────────────────────────────────────────────────────
    condition_ids = fields.One2many(
        'attendance.alert.condition', 'alert_id', string='Conditions', copy=True,
        help='The alert runs when any of these conditions is met.',
    )
    recurrence = fields.Selection(
        [('once', 'Once - archive after it runs'),
         ('recurring', 'Recurring - keep running')],
        string='Runs', default='once', required=True, tracking=True,
    )
    date_start = fields.Date(string='From', help='Leave empty to start straight away.')
    date_end = fields.Date(string='Until', help='Leave empty to run until archived.')
    mon = fields.Boolean(string='Mon', default=True)
    tue = fields.Boolean(string='Tue', default=True)
    wed = fields.Boolean(string='Wed', default=True)
    thu = fields.Boolean(string='Thu', default=True)
    fri = fields.Boolean(string='Fri', default=True)
    sat = fields.Boolean(string='Sat', default=True)
    sun = fields.Boolean(string='Sun', default=True)
    time_from = fields.Float(string='Between', default=0.0, help="In the employee's timezone.")
    time_to = fields.Float(string='And', default=24.0, help="In the employee's timezone.")

    # ── Messages ───────────────────────────────────────────────────────────
    notify_requester = fields.Boolean(
        string='Message Me', default=True,
        help='Send the requester a direct message in Discuss.',
    )
    channel_ids = fields.Many2many(
        'discuss.channel', 'attendance_alert_channel_rel', 'alert_id', 'channel_id',
        string='Post to Channels', domain="[('channel_type', '=', 'channel')]",
        help='Also post the arrival or departure in these Discuss channels.',
    )
    note = fields.Text(
        string='Extra Message',
        help='Added to the message, e.g. "Please collect your parcel from reception."',
    )

    # ── History ────────────────────────────────────────────────────────────
    last_triggered = fields.Datetime(readonly=True, copy=False)
    log_ids = fields.One2many('attendance.alert.log', 'alert_id', string='History', readonly=True)
    log_count = fields.Integer(compute='_compute_log_count')

    @api.depends('log_ids')
    def _compute_log_count(self):
        counts = dict(self.env['attendance.alert.log']._read_group(
            [('alert_id', 'in', self.ids)], ['alert_id'], ['__count'],
        ))
        for alert in self:
            alert.log_count = counts.get(alert, 0)

    @api.constrains('all_employees', 'employee_ids')
    def _check_employees(self):
        for alert in self:
            if not alert.all_employees and not alert.employee_ids:
                raise ValidationError(_('Alert "%s" needs at least one employee to watch.', alert.name))

    @api.constrains('condition_ids')
    def _check_conditions(self):
        for alert in self:
            if not alert.condition_ids:
                raise ValidationError(_('Alert "%s" needs at least one condition.', alert.name))

    @api.constrains('notify_requester', 'channel_ids')
    def _check_destination(self):
        for alert in self:
            if not alert.notify_requester and not alert.channel_ids:
                raise ValidationError(_('Alert "%s" must message you, post to a channel, or both.', alert.name))

    @api.constrains('time_from', 'time_to', 'date_start', 'date_end')
    def _check_window(self):
        for alert in self:
            if not 0 <= alert.time_from < alert.time_to <= 24:
                raise ValidationError(_('The time window must be between 00:00 and 24:00 and end after it starts.'))
            if alert.date_start and alert.date_end and alert.date_end < alert.date_start:
                raise ValidationError(_('"Until" cannot be before "From".'))

    def action_view_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('attendance_kiosks.action_attendance_alert_log')
        action.update({'domain': [('alert_id', '=', self.id)], 'context': {}})
        return action

    # ── Matching ───────────────────────────────────────────────────────────
    def _alert_in_window(self, local_dt):
        """Whether ``local_dt`` (in the employee's timezone) is inside the alert's schedule."""
        self.ensure_one()
        day = local_dt.date()
        if self.date_start and day < self.date_start:
            return False
        if self.date_end and day > self.date_end:
            return False
        if not self[WEEKDAY_FIELDS[local_dt.weekday()]]:
            return False
        hour = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
        return self.time_from <= hour < self.time_to

    @api.model
    def _alert_dispatch(self, attendances, direction):
        """Run the alerts for attendances that just signed in or out.

        :param direction: ``'in'`` or ``'out'``
        """
        for attendance in attendances:
            employee = attendance.employee_id
            candidates = self.sudo().search([
                ('company_id', '=', employee.company_id.id),
                ('condition_ids.event', 'in', [code for code, _label in ALERT_EVENTS
                                               if code.startswith(direction + '_')]),
                '|', ('all_employees', '=', True), ('employee_ids', 'in', employee.ids),
            ])
            if not candidates:
                continue
            events, site, when = attendance._alert_events(direction)
            tz = pytz.timezone(employee._get_tz())
            local = pytz.utc.localize(when).astimezone(tz)
            for alert in candidates:
                if not alert.active or not alert._alert_in_window(local):
                    continue
                condition = alert.condition_ids.filtered(
                    lambda c: c.event in events and (not c.location_ids or site in c.location_ids)
                )[:1]
                if not condition:
                    continue
                try:
                    with self.env.cr.savepoint():
                        alert._alert_fire(attendance, condition, direction, site, local)
                except Exception:
                    _logger.exception('Attendance alert %s failed for attendance %s', alert.id, attendance.id)

    # ── Sending ────────────────────────────────────────────────────────────
    def _alert_message(self, attendance, condition, direction, site, local):
        self.ensure_one()
        employee = attendance.employee_id
        kiosk = attendance.in_kiosk_id if direction == 'in' else (attendance.out_kiosk_id or attendance.in_kiosk_id)
        if direction == 'in':
            verb = _('signed in')
        elif attendance.out_mode == 'auto_check_out':
            verb = _('was automatically signed out')
        else:
            verb = _('signed out')
        where = kiosk.name if kiosk else (site.name if site else '')
        if kiosk and site and site.name not in kiosk.name:
            where = f'{kiosk.name} ({site.name})'
        parts = [Markup('<b>%s</b> %s') % (employee.name, verb)]
        if where:
            parts.append(escape(_('at %s', where)))
        parts.append(escape(_('at %(time)s on %(date)s',
                              time=local.strftime('%H:%M'), date=local.strftime('%d/%m/%Y'))))
        body = Markup(' ').join(parts) + Markup(' - %s.') % dict(ALERT_EVENTS)[condition.event].lower()
        if self.note:
            body += Markup('<br/>') + escape(self.note)
        body += Markup('<br/><i>%s</i>') % _('Alert: %s', self.name)
        return body

    def _alert_requester_chat(self):
        """The direct chat between OdooBot and the requester, created if needed."""
        self.ensure_one()
        Channel = self.env['discuss.channel'].sudo()
        members = self.requester_id.partner_id | self.env.ref('base.partner_root')
        for chat in Channel.search([
            ('channel_type', '=', 'chat'),
            ('channel_member_ids.partner_id', '=', self.requester_id.partner_id.id),
        ]):
            if chat.channel_member_ids.partner_id == members:
                return chat
        return Channel.create({
            'name': ', '.join(members.mapped('name')),
            'channel_type': 'chat',
            'channel_member_ids': [Command.create({'partner_id': partner.id}) for partner in members],
        })

    def _alert_fire(self, attendance, condition, direction, site, local):
        self.ensure_one()
        body = self._alert_message(attendance, condition, direction, site, local)
        odoobot = self.env.ref('base.partner_root')
        if self.notify_requester and self.requester_id.active:
            self._alert_requester_chat().message_post(
                body=body, author_id=odoobot.id, message_type='comment', subtype_xmlid='mail.mt_comment',
            )
        for channel in self.channel_ids.sudo():
            channel.message_post(
                body=body, author_id=odoobot.id, message_type='comment', subtype_xmlid='mail.mt_comment',
            )
        self.env['attendance.alert.log'].sudo().create({
            'alert_id': self.id,
            'employee_id': attendance.employee_id.id,
            'attendance_id': attendance.id,
            'event': condition.event,
            'work_location_id': site.id if site else False,
        })
        vals = {'last_triggered': fields.Datetime.now()}
        if self.recurrence == 'once':
            vals['active'] = False
        self.sudo().write(vals)


class AttendanceAlertCondition(models.Model):
    _name = 'attendance.alert.condition'
    _description = 'Attendance Alert Condition'
    _order = 'alert_id, sequence, id'

    alert_id = fields.Many2one('attendance.alert', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='alert_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    event = fields.Selection(ALERT_EVENTS, string='When', required=True, default='in_first_today')
    location_ids = fields.Many2many(
        'hr.work.location', 'attendance_alert_condition_location_rel', 'condition_id', 'location_id',
        string='Sites', domain="[('company_id', '=', company_id)]",
        help='Only at these work locations. Leave empty for any site.',
    )


class AttendanceAlertLog(models.Model):
    _name = 'attendance.alert.log'
    _description = 'Attendance Alert History'
    _order = 'date desc, id desc'

    alert_id = fields.Many2one('attendance.alert', required=True, ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one(related='alert_id.company_id', store=True)
    requester_id = fields.Many2one(related='alert_id.requester_id', store=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', readonly=True)
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null', readonly=True)
    event = fields.Selection(ALERT_EVENTS, required=True, readonly=True)
    work_location_id = fields.Many2one('hr.work.location', string='Site', readonly=True)


def _day_bounds_utc(when, tz):
    """Naive UTC start and end of the local day containing naive UTC ``when``."""
    local_day = pytz.utc.localize(when).astimezone(tz).date()
    start = tz.localize(datetime.combine(local_day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
    end = tz.localize(datetime.combine(local_day + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
    return start, end
