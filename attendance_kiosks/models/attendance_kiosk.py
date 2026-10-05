import hashlib
import logging
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import ValidationError
from odoo.tools import consteq
from odoo.tools.misc import hmac as hmac_tool
from odoo.tools.safe_eval import datetime as safe_datetime
from odoo.tools.safe_eval import safe_eval
from odoo.tools.safe_eval import time as safe_time

_logger = logging.getLogger(__name__)

# How long a worker's identification at the kiosk stays valid for an action.
TICKET_LIFETIME_SECONDS = 10 * 60


def _new_token(*args):
    return uuid.uuid4().hex


def _iso_utc(dt):
    """Naive UTC datetime -> ISO 8601 string the kiosk JavaScript can parse."""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None


class AttendanceKiosk(models.Model):
    _name = 'attendance.kiosk'
    _description = 'Attendance Kiosk'
    _inherit = ['mail.thread']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, tracking=True,
        default=lambda self: self.env.company,
    )
    work_location_id = fields.Many2one(
        'hr.work.location', string='Work Location', required=True, tracking=True,
        check_company=True, domain="[('company_id', '=', company_id)]",
    )
    tz = fields.Selection(
        _tz_get, string='Timezone', required=True,
        default=lambda self: self.env.user.tz or 'UTC',
        help='Used to work out the day for questionnaires and the time of day for automatic sign out.',
    )

    # ── URL / PWA ──────────────────────────────────────────────────────────
    access_token = fields.Char(
        required=True, copy=False, readonly=True, index=True, default=_new_token,
        groups='hr_attendance.group_hr_attendance_officer',
    )
    offline_salt = fields.Char(
        required=True, copy=False, readonly=True, default=_new_token,
        groups='hr_attendance.group_hr_attendance_manager',
    )
    kiosk_url = fields.Char(
        string='Kiosk URL', compute='_compute_kiosk_url',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    welcome_message = fields.Text(
        help='Shown on the kiosk home screen, e.g. site safety reminders.',
    )
    offline_enabled = fields.Boolean(
        string='Allow Offline Use', default=True,
        help='Keep a copy of who may sign in on the device so the kiosk keeps working '
             'without a connection. Sign ins and sign outs recorded offline are synced '
             'when the connection returns.',
    )
    roster_refresh_minutes = fields.Integer(
        string='Refresh Every (Minutes)', default=15,
        help='How often the kiosk refreshes its offline copy of workers, rules and capabilities.',
    )
    last_contact = fields.Datetime(
        readonly=True, copy=False,
        help='The last time the kiosk device contacted the server.',
    )

    # ── Identification ─────────────────────────────────────────────────────
    identify_badge = fields.Boolean(
        string='Badge Scan', default=True,
        help="Workers sign in by scanning the barcode on their badge (the employee's Badge ID).",
    )
    identify_name = fields.Boolean(
        string='Select Name', default=True,
        help='Workers find and tap their name on the kiosk.',
    )
    require_pin = fields.Boolean(
        string='Require PIN', default=True,
        help="Workers who select their name must also enter their employee PIN.",
    )

    # ── Who can sign in ────────────────────────────────────────────────────
    restrict_to_company = fields.Boolean(
        string="Only This Company's Employees", default=True,
    )
    employee_domain = fields.Char(
        string='Who Can Sign In', default='[]',
        help='Only employees matching this filter can sign in. Leave empty to allow everyone.',
    )
    required_course_ids = fields.Many2many(
        'lms.course', 'attendance_kiosk_required_course_rel', 'kiosk_id', 'course_id',
        string='Minimum Capabilities',
        help='Everyone signing in here must hold a current (completed and unexpired) '
             'record for every one of these Learning courses.',
    )
    rule_ids = fields.One2many('attendance.kiosk.rule', 'kiosk_id', string='Sign In Rules')
    expiry_warning_days = fields.Integer(
        string='Warn Before Expiry (Days)', default=14,
        help='Warn workers on sign in when a capability this kiosk needs expires within '
             'this many days. 0 turns the warning off.',
    )
    eligible_employee_count = fields.Integer(compute='_compute_eligible_employee_count')

    # ── Automatic sign out ─────────────────────────────────────────────────
    auto_sign_out = fields.Boolean(string='Automatic Sign Out', tracking=True)
    auto_sign_out_type = fields.Selection(
        [('duration', 'After a number of hours'), ('time', 'At a time of day')],
        string='Sign Out', default='duration', required=True,
    )
    auto_sign_out_hours = fields.Float(string='After (Hours)', default=12.0)
    auto_sign_out_time = fields.Float(
        string='At (Time of Day)', default=18.0,
        help='Workers still signed in at this time are signed out. Workers who sign in '
             'after this time are signed out at this time the next day.',
    )
    other_sign_in_action = fields.Selection(
        [('sign_out', 'Sign them out here and sign them in there'),
         ('block', 'Refuse until they sign out here')],
        string='Signs In at Another Kiosk', default='sign_out', required=True, tracking=True,
        help='What happens when a worker who is signed in at this kiosk signs in at a different kiosk.',
    )
    other_sign_out_action = fields.Selection(
        [('allow', 'Allow - sign them out from here'),
         ('block', 'Refuse - they must sign out at this kiosk')],
        string='Signs Out at Another Kiosk', default='allow', required=True, tracking=True,
        help='What happens when a worker who is signed in at this kiosk tries to sign out '
             'at a different kiosk.',
    )

    # ── Questionnaires ─────────────────────────────────────────────────────
    questionnaire_line_ids = fields.One2many(
        'attendance.kiosk.questionnaire.line', 'kiosk_id', string='Questionnaires',
    )

    # ── Statistics ─────────────────────────────────────────────────────────
    attendance_count = fields.Integer(compute='_compute_attendance_stats')
    present_count = fields.Integer(string='Signed In Now', compute='_compute_attendance_stats')
    response_count = fields.Integer(compute='_compute_response_count')

    _access_token_unique = models.Constraint(
        'unique (access_token)', 'Each kiosk must have its own URL.',
    )

    @api.depends('access_token')
    def _compute_kiosk_url(self):
        for kiosk in self:
            kiosk.kiosk_url = (
                f'{kiosk.get_base_url()}/kiosk/{kiosk.access_token}' if kiosk.access_token else False
            )

    def _compute_eligible_employee_count(self):
        for kiosk in self:
            kiosk.eligible_employee_count = len(kiosk._kiosk_eligible_employees())

    def _compute_attendance_stats(self):
        Attendance = self.env['hr.attendance']
        totals = dict(Attendance._read_group(
            [('in_kiosk_id', 'in', self.ids)], ['in_kiosk_id'], ['__count'],
        ))
        present = dict(Attendance._read_group(
            [('in_kiosk_id', 'in', self.ids), ('check_out', '=', False)], ['in_kiosk_id'], ['__count'],
        ))
        for kiosk in self:
            kiosk.attendance_count = totals.get(kiosk, 0)
            kiosk.present_count = present.get(kiosk, 0)

    def _compute_response_count(self):
        counts = dict(self.env['attendance.kiosk.response']._read_group(
            [('kiosk_id', 'in', self.ids)], ['kiosk_id'], ['__count'],
        ))
        for kiosk in self:
            kiosk.response_count = counts.get(kiosk, 0)

    @api.constrains('employee_domain')
    def _check_employee_domain(self):
        for kiosk in self:
            kiosk._kiosk_validate_domain(kiosk.employee_domain)

    @api.constrains('auto_sign_out', 'auto_sign_out_type', 'auto_sign_out_hours', 'auto_sign_out_time')
    def _check_auto_sign_out(self):
        for kiosk in self.filtered('auto_sign_out'):
            if kiosk.auto_sign_out_type == 'duration' and kiosk.auto_sign_out_hours <= 0:
                raise ValidationError(_('Automatic sign out needs a number of hours greater than zero.'))
            if kiosk.auto_sign_out_type == 'time' and not 0 <= kiosk.auto_sign_out_time < 24:
                raise ValidationError(_('Automatic sign out time must be between 00:00 and 23:59.'))

    @api.constrains('identify_badge', 'identify_name')
    def _check_identification(self):
        for kiosk in self:
            if not kiosk.identify_badge and not kiosk.identify_name:
                raise ValidationError(_('Kiosk "%s" needs at least one way for workers to identify themselves.', kiosk.name))

    # ── Actions ────────────────────────────────────────────────────────────
    def action_open_kiosk(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.kiosk_url, 'target': 'new'}

    def action_regenerate_url(self):
        for kiosk in self:
            kiosk.sudo().write({'access_token': _new_token(), 'offline_salt': _new_token()})
            kiosk.message_post(body=_('The kiosk URL was regenerated. Devices using the old URL must be set up again.'))

    def action_view_attendances(self):
        self.ensure_one()
        domain = [('in_kiosk_id', '=', self.id)]
        if self.env.context.get('present_only'):
            domain.append(('check_out', '=', False))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendances: %s', self.name),
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'views': [(self.env.ref('hr_attendance.view_attendance_tree').id, 'list'), (False, 'form')],
            'domain': domain,
        }

    def action_view_responses(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('attendance_kiosks.action_attendance_kiosk_response')
        action.update({'domain': [('kiosk_id', '=', self.id)], 'context': {}})
        return action

    def action_view_eligible_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Can Sign In: %s', self.name),
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self._kiosk_eligible_employees().ids)],
        }

    # ── Domains ────────────────────────────────────────────────────────────
    def _kiosk_eval_domain(self, domain):
        """Evaluate a domain built with the rule builder (domain widget)."""
        if not domain or domain.strip() in ('[]', ''):
            return []
        context = {
            'uid': self.env.uid,
            'user': self.env.user,
            'context_today': lambda: fields.Date.context_today(self),
            'datetime': safe_datetime,
            'relativedelta': relativedelta,
            'time': safe_time,
        }
        return safe_eval(domain, context)

    def _kiosk_validate_domain(self, domain):
        try:
            self.env['hr.employee'].sudo().search_count(self._kiosk_eval_domain(domain), limit=1)
        except Exception as error:  # noqa: BLE001 - surface any domain problem to the user
            raise ValidationError(_('The employee filter is not valid: %s', error)) from error

    def _kiosk_base_domain(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.restrict_to_company:
            domain.append(('company_id', '=', self.company_id.id))
        return domain + self._kiosk_eval_domain(self.employee_domain)

    def _kiosk_filter_ids(self, domain, employees):
        """Return the ids of ``employees`` that match ``domain`` (a domain list)."""
        if not domain:
            return set(employees.ids)
        if not employees:
            return set()
        return set(self.env['hr.employee'].sudo().with_context(active_test=False).search(
            domain + [('id', 'in', employees.ids)],
        ).ids)

    def _kiosk_matching_ids(self, domain, employees):
        """Return the ids of ``employees`` that match ``domain`` (a domain string)."""
        return self._kiosk_filter_ids(self._kiosk_eval_domain(domain), employees)

    # ── Eligibility ────────────────────────────────────────────────────────
    def _kiosk_base_employees(self):
        self.ensure_one()
        return self.env['hr.employee'].sudo().search(self._kiosk_base_domain(), order='name')

    def _kiosk_eligible_employees(self):
        self.ensure_one()
        if not self.id:
            return self.env['hr.employee']
        employees = self._kiosk_base_employees()
        evaluation = self._kiosk_evaluate(employees)
        return employees.filtered(lambda e: evaluation[e.id]['ok'])

    def _kiosk_evaluate(self, employees):
        """Work out whether each employee may sign in at this kiosk.

        :return: ``{employee_id: {'ok': bool, 'reasons': [str], 'warnings': [str],
            'until': 'YYYY-MM-DD' or None}}``. ``until`` is the last day the
            capabilities the employee relies on are current, so an offline
            kiosk can stop them signing in once one expires.
        """
        self.ensure_one()
        employees = employees.sudo()
        base_ids = self._kiosk_filter_ids(self._kiosk_base_domain(), employees)
        rules = self.rule_ids.filtered('active').sorted('sequence')
        courses = self.required_course_ids | rules.required_course_ids | rules.any_course_ids
        capabilities = employees._kiosk_current_capabilities(courses)
        rule_matches = {
            rule.id: (
                self._kiosk_matching_ids(rule.applies_domain, employees),
                self._kiosk_matching_ids(rule.requirement_domain, employees)
                if rule.rule_type == 'require' else set(),
            )
            for rule in rules
        }
        today = fields.Date.context_today(self)
        warn_until = today + timedelta(days=self.expiry_warning_days) if self.expiry_warning_days > 0 else None

        result = {}
        for employee in employees:
            held = capabilities[employee.id]
            reasons, warnings, relied = [], [], {}

            def require_all(course_set, reasons=reasons, relied=relied, held=held):
                missing = course_set.filtered(lambda c: c.id not in held)
                if missing:
                    reasons.append(self.env._('Missing or expired: %s', ', '.join(missing.mapped('name'))))
                for course in course_set - missing:
                    relied[course] = held[course.id]

            if employee.id not in base_ids:
                reasons.append(_('You are not permitted to sign in at this kiosk.'))
            else:
                require_all(self.required_course_ids)
                for rule in rules:
                    applies, meets = rule_matches[rule.id]
                    if employee.id not in applies:
                        continue
                    if rule.rule_type == 'deny':
                        reasons.append(rule.message or _('Sign in refused: %s', rule.name))
                        continue
                    problems = []
                    if employee.id not in meets:
                        problems.append(_('requirements not met'))
                    missing = rule.required_course_ids.filtered(lambda c: c.id not in held)
                    if missing:
                        problems.append(_('missing or expired: %s', ', '.join(missing.mapped('name'))))
                    held_any = rule.any_course_ids.filtered(lambda c: c.id in held)
                    if rule.any_course_ids and not held_any:
                        problems.append(_('needs one of: %s', ', '.join(rule.any_course_ids.mapped('name'))))
                    if problems:
                        reasons.append(rule.message or '%s - %s' % (rule.name, '; '.join(problems)))
                        continue
                    for course in rule.required_course_ids:
                        relied[course] = held[course.id]
                    if held_any:
                        # The longest-lasting capability of the "any of" set keeps the rule met.
                        best = max(held_any, key=lambda c: held[c.id] or date.max)
                        relied[best] = held[best.id]

            dated = {course: expiry for course, expiry in relied.items() if expiry}
            until = min(dated.values()) if dated else None
            if warn_until:
                for course, expiry in sorted(dated.items(), key=lambda item: item[1]):
                    if expiry <= warn_until:
                        warnings.append(_('Your %(course)s expires on %(date)s.',
                                          course=course.name, date=expiry.strftime('%d/%m/%Y')))
            result[employee.id] = {
                'ok': not reasons,
                'reasons': reasons,
                'warnings': warnings,
                'until': until.isoformat() if until else None,
            }
        return result

    # ── Time helpers ───────────────────────────────────────────────────────
    def _kiosk_tz(self):
        self.ensure_one()
        try:
            return pytz.timezone(self.tz or 'UTC')
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _kiosk_local_date(self, dt):
        """Naive UTC datetime -> date at the kiosk."""
        return pytz.utc.localize(dt).astimezone(self._kiosk_tz()).date()

    def _kiosk_format_time(self, dt):
        return pytz.utc.localize(dt).astimezone(self._kiosk_tz()).strftime('%H:%M')

    def _kiosk_format_datetime(self, dt):
        return pytz.utc.localize(dt).astimezone(self._kiosk_tz()).strftime('%d/%m/%Y %H:%M')

    def _kiosk_auto_sign_out_due(self, check_in):
        """When an attendance that started at ``check_in`` here is signed out automatically.

        :param check_in: naive UTC datetime
        :return: naive UTC datetime, or None when automatic sign out is off
        """
        self.ensure_one()
        if not self.auto_sign_out:
            return None
        if self.auto_sign_out_type == 'duration':
            if self.auto_sign_out_hours <= 0:
                return None
            return check_in + timedelta(hours=self.auto_sign_out_hours)
        tz = self._kiosk_tz()
        local_in = pytz.utc.localize(check_in).astimezone(tz)
        minutes = min(round(self.auto_sign_out_time * 60), 24 * 60 - 1)
        at = time(minutes // 60, minutes % 60)
        due = tz.localize(datetime.combine(local_in.date(), at))
        if due <= local_in:
            due = tz.localize(datetime.combine(local_in.date() + timedelta(days=1), at))
        return due.astimezone(pytz.utc).replace(tzinfo=None)

    # ── Automatic sign out ─────────────────────────────────────────────────
    def _kiosk_apply_auto_sign_out(self, attendance, due):
        self.ensure_one()
        attendance.sudo().write({
            'check_out': max(due, attendance.check_in),
            'out_mode': 'auto_check_out',
            'out_kiosk_id': self.id,
        })
        attendance.sudo().message_post(body=_(
            'Automatically signed out by kiosk %(kiosk)s at %(time)s.',
            kiosk=self.name, time=self._kiosk_format_datetime(attendance.check_out),
        ))

    @api.model
    def _cron_auto_sign_out(self):
        now = fields.Datetime.now()
        attendances = self.env['hr.attendance'].sudo().search([
            ('check_out', '=', False),
            ('in_kiosk_id.auto_sign_out', '=', True),
        ])
        for attendance in attendances:
            kiosk = attendance.in_kiosk_id
            due = kiosk._kiosk_auto_sign_out_due(attendance.check_in)
            if due and due <= now:
                try:
                    with self.env.cr.savepoint():
                        kiosk._kiosk_apply_auto_sign_out(attendance, due)
                except Exception:
                    _logger.exception('Automatic sign out failed for attendance %s', attendance.id)

    def _kiosk_open_attendance(self, employee, now):
        """The employee's open attendance, after applying any overdue automatic sign out."""
        attendance = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id), ('check_out', '=', False),
        ], order='check_in desc', limit=1)
        if attendance and attendance.in_kiosk_id:
            due = attendance.in_kiosk_id._kiosk_auto_sign_out_due(attendance.check_in)
            if due and due <= now:
                attendance.in_kiosk_id._kiosk_apply_auto_sign_out(attendance, due)
                return self.env['hr.attendance']
        return attendance

    # ── Questionnaires ─────────────────────────────────────────────────────
    def _kiosk_active_questionnaire_lines(self):
        return self.questionnaire_line_ids.filtered(
            lambda line: line.questionnaire_id.active and line.questionnaire_id.question_ids
        ).sorted('sequence')

    def _kiosk_history(self, employees):
        """Last sign in dates the questionnaire triggers depend on.

        :return: ``{employee_id: {'any': 'YYYY-MM-DD' or None, 'loc': 'YYYY-MM-DD' or None}}``
            - the kiosk-local date of the employee's last sign in anywhere, and
            at this kiosk's work location.
        """
        self.ensure_one()
        Attendance = self.env['hr.attendance'].sudo()
        last_any = dict(Attendance._read_group(
            [('employee_id', 'in', employees.ids)], ['employee_id'], ['check_in:max'],
        ))
        last_loc = dict(Attendance._read_group(
            [('employee_id', 'in', employees.ids), ('kiosk_work_location_id', '=', self.work_location_id.id)],
            ['employee_id'], ['check_in:max'],
        ))

        def as_date(dt):
            return self._kiosk_local_date(dt).isoformat() if dt else None

        return {
            employee.id: {'any': as_date(last_any.get(employee)), 'loc': as_date(last_loc.get(employee))}
            for employee in employees
        }

    def _kiosk_line_targets(self, employees):
        """``{line_id: set(employee ids)}`` - who each questionnaire line applies to."""
        return {
            line.id: self._kiosk_matching_ids(line.employee_domain, employees)
            for line in self._kiosk_active_questionnaire_lines()
        }

    def _kiosk_questionnaires_due(self, employee, now):
        """Questionnaires the employee must answer to sign in now."""
        self.ensure_one()
        history = self._kiosk_history(employee)[employee.id]
        targets = self._kiosk_line_targets(employee)
        today = self._kiosk_local_date(now).isoformat()
        due = self.env['attendance.kiosk.questionnaire']
        for line in self._kiosk_active_questionnaire_lines():
            if employee.id not in targets[line.id]:
                continue
            if line._is_due(history, today):
                due |= line.questionnaire_id
        return due

    # ── Kiosk payloads ─────────────────────────────────────────────────────
    def _kiosk_hash(self, value):
        if not value:
            return None
        return hashlib.sha256(f'{self.sudo().offline_salt}:{value}'.encode()).hexdigest()

    def _kiosk_open_payload(self, attendance):
        if not attendance:
            return None
        other = attendance.in_kiosk_id
        due = other._kiosk_auto_sign_out_due(attendance.check_in) if other else None
        return {
            'kiosk_id': other.id or None,
            'kiosk_name': other.name or _('Attendances app'),
            'check_in': _iso_utc(attendance.check_in),
            'auto_out': _iso_utc(due),
            'block_in': bool(other and other.id != self.id and other.other_sign_in_action == 'block'),
            'block_out': bool(other and other.id != self.id and other.other_sign_out_action == 'block'),
        }

    def _kiosk_employee_payloads(self, employees):
        """Everything the kiosk needs to know about these employees, online or offline."""
        self.ensure_one()
        employees = employees.sudo()
        evaluation = self._kiosk_evaluate(employees)
        history = self._kiosk_history(employees)
        targets = self._kiosk_line_targets(employees)
        open_attendances = {
            attendance.employee_id.id: attendance
            for attendance in self.env['hr.attendance'].sudo().search(
                [('employee_id', 'in', employees.ids), ('check_out', '=', False)], order='check_in',
            )
        }
        payloads = []
        for employee in employees:
            payloads.append({
                'id': employee.id,
                'name': employee.name,
                'job': employee.job_title or '',
                'avatar': f'/kiosk/{self.sudo().access_token}/avatar/{employee.id}',
                'badge': self._kiosk_hash(employee.barcode) if self.offline_enabled else None,
                'pin': self._kiosk_hash(employee.pin) if self.offline_enabled else None,
                'has_pin': bool(employee.pin),
                **evaluation[employee.id],
                'open': self._kiosk_open_payload(open_attendances.get(employee.id)),
                'history': history[employee.id],
                'lines': [line_id for line_id, ids in targets.items() if employee.id in ids],
            })
        return payloads

    def _kiosk_config(self):
        self.ensure_one()
        lines = self._kiosk_active_questionnaire_lines()
        return {
            'id': self.id,
            'name': self.name,
            'company': self.company_id.name,
            'location': self.work_location_id.name,
            'welcome': self.welcome_message or '',
            'identify_badge': self.identify_badge,
            'identify_name': self.identify_name,
            'require_pin': self.require_pin,
            'offline': self.offline_enabled,
            'refresh_minutes': max(self.roster_refresh_minutes, 1),
            'salt': self.sudo().offline_salt if self.offline_enabled else None,
            'auto_sign_out': {
                'enabled': self.auto_sign_out,
                'type': self.auto_sign_out_type,
                'hours': self.auto_sign_out_hours,
                'time': self.auto_sign_out_time,
            },
            'lines': [{
                'id': line.id,
                'questionnaire_id': line.questionnaire_id.id,
                'trigger': line.trigger,
            } for line in lines],
            'questionnaires': [q._kiosk_payload() for q in lines.questionnaire_id],
            'server_time': _iso_utc(fields.Datetime.now()),
        }

    # ── Identification tickets ─────────────────────────────────────────────
    def _kiosk_make_ticket(self, employee):
        self.ensure_one()
        issued = int(time_module.time())
        message = f'{self.id}:{employee.id}:{issued}'
        signature = hmac_tool(self.env(su=True), 'attendance_kiosk', message)
        return f'{message}:{signature}'

    def _kiosk_check_ticket(self, ticket, employee_id):
        self.ensure_one()
        try:
            kiosk_id, emp_id, issued, signature = (ticket or '').split(':')
            kiosk_id, emp_id, issued = int(kiosk_id), int(emp_id), int(issued)
        except ValueError:
            return False
        if kiosk_id != self.id or emp_id != employee_id:
            return False
        if time_module.time() - issued > TICKET_LIFETIME_SECONDS:
            return False
        expected = hmac_tool(self.env(su=True), 'attendance_kiosk', f'{kiosk_id}:{emp_id}:{issued}')
        return consteq(expected, signature)

    # ── Sign in / sign out ─────────────────────────────────────────────────
    def _kiosk_attendance_location(self):
        return f'{self.name} ({self.work_location_id.name})'

    def _kiosk_sign_in(self, employee, when, answers, offline=False, event=None):
        """Sign ``employee`` in at this kiosk.

        Online, the sign in rules, other-kiosk settings and questionnaires are
        enforced. Offline events were already checked by the kiosk with the
        data it had, so they are recorded as they happened.

        :param when: naive UTC datetime of the sign in
        :param answers: questionnaire answers posted by the kiosk
        :param event: id of the offline event, so a re-sent event is applied once
        :return: result dict for the kiosk
        """
        self.ensure_one()
        employee = employee.sudo()
        if event and self.env['hr.attendance'].sudo().search_count([('kiosk_event_in', '=', event)], limit=1):
            return {'status': 'signed_in', 'duplicate': True}
        attendance = self._kiosk_open_attendance(employee, when)
        if attendance and attendance.in_kiosk_id == self:
            if offline:
                return {'status': 'signed_in', 'duplicate': True}
            return {'status': 'error', 'message': _('You are already signed in here.')}

        if not offline:
            evaluation = self._kiosk_evaluate(employee)[employee.id]
            if not evaluation['ok']:
                return {'status': 'refused', 'reasons': evaluation['reasons']}
            if attendance and self._kiosk_open_payload(attendance)['block_in']:
                return {'status': 'error', 'message': _(
                    'You are signed in at %(kiosk)s. Please sign out there first.',
                    kiosk=attendance.in_kiosk_id.name,
                )}

        questionnaires = self._kiosk_questionnaires_due(employee, when)
        if offline:
            # Record whatever the kiosk asked, even if the rules have changed since.
            answered = {int(a.get('questionnaire_id') or 0) for a in answers or []}
            questionnaires = self.env['attendance.kiosk.questionnaire'].sudo().browse(
                [qid for qid in answered if qid]).exists()
        response_vals, blocked, missing = self.env['attendance.kiosk.response']._kiosk_prepare(
            self, employee, questionnaires, answers, when, strict=not offline,
        )
        if missing:
            return {
                'status': 'questionnaire_required',
                'questionnaire_ids': missing.ids,
                'message': _('Please answer every question.'),
            }
        Response = self.env['attendance.kiosk.response'].sudo()
        if blocked:
            for vals in response_vals:
                vals['blocked'] = True
            Response.create(response_vals)
            return {'status': 'blocked', 'messages': blocked}

        if attendance:
            if attendance.check_in > when:
                return {'status': 'error', 'message': _(
                    'A later sign in already exists for %s.', employee.name)}
            attendance.write({
                'check_out': when,
                'out_mode': 'kiosk',
                'out_kiosk_id': self.id,
                'kiosk_transferred': True,
                'kiosk_offline_out': offline,
            })
        new_attendance = self.env['hr.attendance'].sudo().create({
            'employee_id': employee.id,
            'check_in': when,
            'in_mode': 'kiosk',
            'in_location': self._kiosk_attendance_location(),
            'in_kiosk_id': self.id,
            'kiosk_offline_in': offline,
            'kiosk_event_in': event or False,
        })
        for vals in response_vals:
            vals['attendance_id'] = new_attendance.id
        Response.create(response_vals)
        return {
            'status': 'signed_in',
            'time': _iso_utc(new_attendance.check_in),
            'open': self._kiosk_open_payload(new_attendance),
            'transferred_from': attendance.in_kiosk_id.name if attendance else None,
        }

    def _kiosk_sign_out(self, employee, when, offline=False, event=None):
        self.ensure_one()
        employee = employee.sudo()
        Attendance = self.env['hr.attendance'].sudo()
        if event and Attendance.search_count([('kiosk_event_out', '=', event)], limit=1):
            return {'status': 'signed_out', 'duplicate': True}
        attendance = self._kiosk_open_attendance(employee, when)
        if not attendance:
            if offline:
                # Signed out offline after the server had already signed them out
                # automatically: keep the time the worker actually left.
                last = Attendance.search([('employee_id', '=', employee.id)], order='check_in desc', limit=1)
                if last and last.out_mode == 'auto_check_out' and last.check_in <= when:
                    last.write({'check_out': when, 'out_mode': 'kiosk', 'out_kiosk_id': self.id,
                                'kiosk_offline_out': True, 'kiosk_event_out': event or False})
                    last.message_post(body=_('Sign out time corrected from the offline kiosk %s.', self.name))
                    return {'status': 'signed_out', 'time': _iso_utc(when)}
                return {'status': 'signed_out', 'duplicate': True}
            return {'status': 'error', 'message': _('You are not signed in.')}
        if not offline and self._kiosk_open_payload(attendance)['block_out']:
            return {'status': 'error', 'message': _(
                'You signed in at %(kiosk)s, so you must sign out there.', kiosk=attendance.in_kiosk_id.name)}
        if attendance.check_in > when:
            if offline:
                return {'status': 'error', 'message': _(
                    'A later sign in already exists for %s.', employee.name)}
            when = attendance.check_in
        attendance.write({
            'check_out': when,
            'out_mode': 'kiosk',
            'out_kiosk_id': self.id,
            'kiosk_offline_out': offline,
            'kiosk_event_out': event or False,
        })
        return {
            'status': 'signed_out',
            'time': _iso_utc(attendance.check_out),
            'check_in': _iso_utc(attendance.check_in),
            'worked_hours': attendance.worked_hours,
        }
