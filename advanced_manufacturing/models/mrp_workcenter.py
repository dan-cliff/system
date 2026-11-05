# -*- coding: utf-8 -*-
"""Work Centre app: a login-free Progressive Web App for each work centre.

Each work centre has its own URL (/manufacturing/workcentre/<token>). Workers
sign in with their ID badge (camera or reader) or by selecting their name and
entering their PIN, as chosen in Manufacturing's Settings (the same choices
as On Site's sign in kiosks). They start, pause and finish the work centre's
work orders, record what they produced and, with Checklists, fill in QA
checklists. The app keeps a copy of its workers and work orders, so it keeps
working offline; what it records offline is synced when the connection
returns (see controllers/terminal.py).
"""
import hashlib
import re
import time as time_module
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import consteq
from odoo.tools.misc import hmac as hmac_tool

# How long a worker stays identified to the server after signing in.
TICKET_LIFETIME_SECONDS = 12 * 60 * 60


def _new_token(*args):
    return uuid.uuid4().hex


def normalize_badge(code):
    """Badge ID as compared by the Work Centre app: no spaces or control characters,
    upper case, without the leading zeros RFID readers often add (terminal.js does
    the same, as does On Site's kiosk)."""
    code = re.sub(r'[\s\x00-\x1f\x7f]+', '', str(code or '')).upper()
    return re.sub(r'^0+(?=.)', '', code)


def iso_utc(dt):
    """Naive UTC datetime -> ISO 8601 string the app's JavaScript can parse."""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    # Working Hours may belong to the work centre's company or to any company
    # above it (e.g. a group's shared hours), not only to its own company as
    # Odoo's company check requires (see _check_resource_calendar_company).
    resource_calendar_id = fields.Many2one(
        check_company=False,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', calendar_company_ids)]",
    )
    calendar_company_ids = fields.Many2many(
        'res.company', compute='_compute_calendar_company_ids',
        help='Companies whose Working Hours this work centre can use: its company and the companies above it.',
    )

    terminal_token = fields.Char(
        string='Work Centre App Token', copy=False, readonly=True, index=True, default=_new_token,
        groups='mrp.group_mrp_user',
    )
    terminal_salt = fields.Char(
        copy=False, readonly=True, default=_new_token, groups='mrp.group_mrp_manager',
    )
    terminal_url = fields.Char(
        string='Work Centre App URL', compute='_compute_terminal_url', groups='mrp.group_mrp_user',
        help='Open this link on the device at the work centre and install it as an app.',
    )
    terminal_employee_ids = fields.Many2many(
        'hr.employee', 'mrp_workcenter_terminal_employee_rel', 'workcenter_id', 'employee_id',
        string='Operators',
        help='Only these employees can sign in to this work centre. Leave empty to let every '
             "employee of the work centre's company sign in.",
    )
    terminal_message = fields.Text(
        string='Message for Workers',
        help='Shown on the Work Centre app, e.g. safety reminders for this work centre.',
    )
    terminal_last_contact = fields.Datetime(
        string='Last Contact', readonly=True, copy=False,
        help='The last time the Work Centre app on this work centre reached Odoo.',
    )
    terminal_event_ids = fields.One2many(
        'advanced.manufacturing.terminal.event', 'workcenter_id', string='Work Centre App Log',
    )
    terminal_failed_count = fields.Integer(compute='_compute_terminal_failed_count')

    @api.depends('company_id')
    def _compute_calendar_company_ids(self):
        for workcenter in self:
            workcenter.calendar_company_ids = workcenter.company_id.sudo().parent_ids

    @api.constrains('resource_calendar_id', 'company_id')
    def _check_resource_calendar_company(self):
        for workcenter in self:
            calendar_company = workcenter.resource_calendar_id.sudo().company_id
            if calendar_company and calendar_company not in workcenter.company_id.sudo().parent_ids:
                raise ValidationError(_(
                    'The Working Hours "%(calendar)s" belong to %(calendar_company)s. Work centre "%(workcenter)s" '
                    'can only use Working Hours of %(company)s or a company above it.',
                    calendar=workcenter.resource_calendar_id.name, calendar_company=calendar_company.name,
                    workcenter=workcenter.name, company=workcenter.company_id.name or _('no company'),
                ))

    @api.depends('terminal_token')
    def _compute_terminal_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for workcenter in self:
            token = workcenter.sudo().terminal_token
            workcenter.terminal_url = f'{base}/manufacturing/workcentre/{token}' if token else False

    def _compute_terminal_failed_count(self):
        counts = dict(self.env['advanced.manufacturing.terminal.event'].sudo()._read_group(
            [('workcenter_id', 'in', self.ids), ('state', '=', 'failed')], ['workcenter_id'], ['__count']))
        for workcenter in self:
            workcenter.terminal_failed_count = counts.get(workcenter, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('terminal_token', _new_token())
            vals.setdefault('terminal_salt', _new_token())
        return super().create(vals_list)

    # ── Buttons ────────────────────────────────────────────────────────────
    def action_open_terminal(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.terminal_url, 'target': 'new'}

    def action_regenerate_terminal_url(self):
        if not self.env.user.has_group('mrp.group_mrp_manager'):
            raise UserError(_('Only Manufacturing Administrators can give a work centre a new link.'))
        for workcenter in self.sudo():
            workcenter.write({'terminal_token': _new_token(), 'terminal_salt': _new_token()})
            workcenter.message_post(body=_('The Work Centre app has a new link. Devices using the old one must be set up again.'))
        return True

    def action_view_terminal_events(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_manufacturing.action_terminal_event')
        action['domain'] = [('workcenter_id', '=', self.id)]
        action['context'] = {'search_default_failed': 1}
        return action

    # ── Who can sign in ────────────────────────────────────────────────────
    def _terminal_employee_domain(self):
        self.ensure_one()
        domain = [('company_id', 'in', [False, self.company_id.id])] if self.company_id else []
        if self.terminal_employee_ids:
            domain.append(('id', 'in', self.terminal_employee_ids.ids))
        return domain

    def _terminal_employees(self):
        self.ensure_one()
        return self.env['hr.employee'].sudo().search(self._terminal_employee_domain(), order='name')

    def _terminal_can_use(self, employee):
        self.ensure_one()
        return bool(employee and employee.sudo().filtered_domain(self._terminal_employee_domain()))

    def _terminal_refusals(self, employees):
        """{employee id: [reasons they can't work here now]}. Bridges add their own
        (e.g. On Site: not signed in at work)."""
        return {employee.id: [] for employee in employees}

    def _terminal_find_badge(self, code):
        """The employee allowed here whose Badge ID matches a scanned code, ignoring
        spaces, letter case and leading zeros. None when no single one matches."""
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        raw = str(code or '').strip()
        if not raw:
            return None
        domain = self._terminal_employee_domain()
        exact = Employee.search(domain + [('barcode', '=', raw)], limit=2)
        if len(exact) == 1:
            return exact
        wanted = normalize_badge(raw)
        if not wanted:
            return None
        candidates = Employee.search(domain + [('barcode', 'ilike', wanted)])
        matches = candidates.filtered(lambda e: normalize_badge(e.barcode) == wanted)
        return matches if len(matches) == 1 else None

    # ── Payloads ───────────────────────────────────────────────────────────
    def _terminal_company(self):
        return self.company_id or self.env.company

    def _terminal_hash(self, value):
        if not value:
            return None
        return hashlib.sha256(f'{self.sudo().terminal_salt}:{value}'.encode()).hexdigest()

    def _terminal_employee_payloads(self, employees):
        self.ensure_one()
        employees = employees.sudo()
        offline = self._terminal_company().mrp_terminal_offline
        refusals = self._terminal_refusals(employees)
        token = self.sudo().terminal_token
        return [{
            'id': employee.id,
            'name': employee.name,
            'job': employee.job_title or '',
            'avatar': f'/manufacturing/workcentre/{token}/avatar/{employee.id}',
            'badge': self._terminal_hash(normalize_badge(employee.barcode)) if offline else None,
            'pin': self._terminal_hash(employee.pin) if offline else None,
            'has_pin': bool(employee.pin),
            'refusals': refusals.get(employee.id, []),
        } for employee in employees]

    def _terminal_workorders(self):
        self.ensure_one()
        return self.env['mrp.workorder'].sudo().search([
            ('workcenter_id', '=', self.id),
            ('state', 'in', ('blocked', 'ready', 'progress')),
            ('production_state', 'not in', ('draft', 'done', 'cancel')),
        ], order='date_start, id', limit=200)

    def _terminal_config(self):
        self.ensure_one()
        company = self._terminal_company()
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code or '',
            'company': company.name,
            'message': self.terminal_message or '',
            'identify_badge': company.mrp_terminal_identify_badge,
            'identify_reader': company.mrp_terminal_identify_reader,
            'identify_name': company.mrp_terminal_identify_name,
            'require_pin': company.mrp_terminal_require_pin,
            'idle_minutes': max(company.mrp_terminal_idle_minutes, 0),
            'offline': company.mrp_terminal_offline,
            'offline_hours': max(company.mrp_terminal_offline_hours, 1),
            'refresh_minutes': max(company.mrp_terminal_refresh_minutes, 1),
            'close_production': company.mrp_terminal_close_production,
            'salt': self.sudo().terminal_salt if company.mrp_terminal_offline else None,
            'server_time': iso_utc(fields.Datetime.now()),
            # Bridges add their own features here (e.g. Checklists: 'qa').
            'features': {},
        }

    def _terminal_data(self):
        """Everything the app keeps a copy of: workers and work orders."""
        self.ensure_one()
        workorders = self._terminal_workorders()
        return {
            'server_time': iso_utc(fields.Datetime.now()),
            'employees': self._terminal_employee_payloads(self._terminal_employees()),
            'workorders': [workorder._terminal_payload() for workorder in workorders],
        }

    # ── Identification tickets ─────────────────────────────────────────────
    def _terminal_make_ticket(self, employee):
        self.ensure_one()
        issued = int(time_module.time())
        message = f'{self.id}:{employee.id}:{issued}'
        signature = hmac_tool(self.env(su=True), 'advanced_manufacturing_terminal', message)
        return f'{message}:{signature}'

    def _terminal_check_ticket(self, ticket, employee_id):
        self.ensure_one()
        try:
            workcenter_id, emp_id, issued, signature = (ticket or '').split(':')
            workcenter_id, emp_id, issued = int(workcenter_id), int(emp_id), int(issued)
        except ValueError:
            return False
        if workcenter_id != self.id or emp_id != employee_id:
            return False
        if time_module.time() - issued > TICKET_LIFETIME_SECONDS:
            return False
        expected = hmac_tool(self.env(su=True), 'advanced_manufacturing_terminal', f'{workcenter_id}:{emp_id}:{issued}')
        return consteq(expected, signature)

    # ── Recording work ─────────────────────────────────────────────────────
    @api.model
    def _terminal_actions(self):
        """Event actions the app may send, {action: workorder method}. Bridges add theirs."""
        return {
            'start': '_terminal_start',
            'pause': '_terminal_pause',
            'produce': '_terminal_produce',
            'finish': '_terminal_finish',
        }

    def _terminal_apply(self, event, employee, when, offline=False):
        """Apply one event from the app, once: an event id already applied returns
        its first result again, so a re-sent offline event can't double up.

        :param event: dict from the app ({id, action, workorder_id, ...})
        :param when: naive UTC datetime the worker did it
        :return: {'status': 'ok' | 'error', 'message': ...}
        """
        self.ensure_one()
        Log = self.env['advanced.manufacturing.terminal.event'].sudo()
        event_id = str(event.get('id') or '')[:64]
        if event_id:
            done = Log.search([('name', '=', event_id), ('workcenter_id', '=', self.id)], limit=1)
            if done:
                return {'status': 'ok' if done.state == 'done' else 'error', 'message': done.message or '',
                        'duplicate': True}
        action = event.get('action')
        method = self._terminal_actions().get(action)
        workorder = self.env['mrp.workorder'].sudo()
        try:
            workorder = workorder.browse(int(event.get('workorder_id') or 0)).exists()
        except (TypeError, ValueError):
            pass
        result = {'status': 'ok', 'message': ''}
        if not method:
            result = {'status': 'error', 'message': _('Unknown action.')}
        elif not workorder or workorder.workcenter_id != self:
            result = {'status': 'error', 'message': _('This work order is no longer at this work centre.')}
        else:
            try:
                with self.env.cr.savepoint():
                    message = getattr(workorder, method)(employee, when, event)
                    result['message'] = message or ''
            except (UserError, ValidationError) as error:
                result = {'status': 'error', 'message': str(error.args[0] if error.args else error)}
        Log.create({
            'name': event_id or _new_token(),
            'workcenter_id': self.id,
            'employee_id': employee.id,
            'workorder_id': workorder.id or False,
            'production_id': workorder.production_id.id or False,
            'action': action if action in dict(Log._fields['action'].selection) else 'other',
            'event_time': when,
            'offline': offline,
            'state': 'done' if result['status'] == 'ok' else 'failed',
            'message': result['message'],
        })
        if result['status'] == 'error' and offline:
            self.message_post(body=_(
                'Work recorded offline by %(employee)s could not be synced and needs checking: %(error)s',
                employee=employee.name, error=result['message'],
            ))
        return result
