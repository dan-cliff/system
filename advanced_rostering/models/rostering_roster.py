# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .rostering_tools import CYCLE_WEEKS, CYCLES, get_cycle, period_bounds


class RosteringRoster(models.Model):
    _name = 'rostering.roster'
    _description = 'Roster'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name, id desc'
    # Publishers and approvers post on records they can read but not edit.
    _mail_post_access = 'read'

    name = fields.Char(string='Roster', required=True, tracking=True, default=lambda self: _('Roster'),
                       help='e.g. the team or site the roster is for.')
    date_start = fields.Date(
        string='From', required=True, index=True, tracking=True, default=fields.Date.context_today,
        help='On a new roster, pick any day: the roster covers the whole period (week, fortnight, '
             'month or quarter, from Settings) containing it.',
    )
    date_end = fields.Date(string='To', required=True, index=True, readonly=True, tracking=True)
    cycle = fields.Selection(CYCLES, string='Cycle', readonly=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('published', 'Published')],
        string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True, index=True,
    )
    shift_ids = fields.One2many('rostering.shift', 'roster_id', string='Shifts', copy=True)
    shift_count = fields.Integer(string='Shift Count', compute='_compute_totals')
    total_hours = fields.Float(string='Paid Hours', compute='_compute_totals')
    person_count = fields.Integer(string='People', compute='_compute_totals')
    unassigned_count = fields.Integer(string='Unassigned Shifts', compute='_compute_totals')
    leave_conflict_count = fields.Integer(string='Shifts on Leave', compute='_compute_leave_conflict_count')
    public_holiday_ids = fields.Many2many(
        'rostering.public.holiday', string='Public Holidays', compute='_compute_public_holiday_ids',
        help='Public holidays in the roster\'s period that apply to the company or anyone on the roster.',
    )
    public_holiday_count = fields.Integer(string='Public Holiday Count', compute='_compute_public_holiday_ids')
    published_date = fields.Datetime(string='Published On', readonly=True, copy=False)
    published_by_id = fields.Many2one('res.users', string='Published By', readonly=True, copy=False)
    note = fields.Html(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, tracking=True,
                                 default=lambda self: self.env.company)
    can_edit = fields.Boolean(compute='_compute_permissions')
    can_publish = fields.Boolean(compute='_compute_permissions')
    can_unpublish = fields.Boolean(compute='_compute_permissions')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('name', 'date_start', 'date_end')
    def _compute_display_name(self):
        for roster in self:
            dates = ' – '.join(d.strftime('%d/%m/%Y') for d in (roster.date_start, roster.date_end) if d)
            roster.display_name = ' '.join(part for part in (roster.name, dates) if part)

    @api.depends('shift_ids.paid_hours', 'shift_ids.user_id', 'shift_ids.person_name')
    def _compute_totals(self):
        for roster in self:
            shifts = roster.shift_ids
            roster.shift_count = len(shifts)
            roster.total_hours = sum(shifts.mapped('paid_hours'))
            assigned = shifts.filtered('is_assigned')
            roster.person_count = len(set(assigned.mapped('person_name')))
            roster.unassigned_count = len(shifts - assigned)

    def _compute_leave_conflict_count(self):
        for roster in self:
            roster.leave_conflict_count = len(roster.shift_ids.filtered('on_leave'))

    @api.depends('date_start', 'date_end', 'company_id', 'shift_ids.date')
    def _compute_public_holiday_ids(self):
        Jurisdiction = self.env['rostering.holiday.jurisdiction']
        for roster in self:
            holidays = self.env['rostering.public.holiday']
            if roster.date_start and roster.date_end:
                jurisdictions = Jurisdiction._for_company(roster.company_id or self.env.company)
                jurisdictions |= roster.shift_ids._all_holiday_jurisdictions()
                holidays = holidays._in_range(roster.date_start, roster.date_end)._applying_to(
                    jurisdictions, roster.company_id)
            roster.public_holiday_ids = holidays
            roster.public_holiday_count = len(holidays)

    @api.depends('state')
    @api.depends_context('uid')
    def _compute_permissions(self):
        user = self.env.user
        edit_draft = user.has_group('advanced_rostering.group_roster_edit_draft')
        edit_published = user.has_group('advanced_rostering.group_roster_edit_published')
        publish = user.has_group('advanced_rostering.group_roster_publish')
        unpublish = user.has_group('advanced_rostering.group_roster_unpublish')
        for roster in self:
            draft = roster.state == 'draft'
            roster.can_edit = edit_draft if draft else edit_published
            roster.can_publish = draft and publish
            roster.can_unpublish = not draft and unpublish

    # ------------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            day = fields.Date.to_date(vals.get('date_start')) or fields.Date.context_today(self)
            cycle = get_cycle(self.env)
            start, end = period_bounds(self.env, day, cycle)
            vals.update(date_start=start, date_end=end, cycle=cycle)
        return super().create(vals_list)

    def write(self, vals):
        if 'date_start' in vals and not self.env.su:
            raise UserError(_('A roster keeps its period. Create a new roster for another period.'))
        return super().write(vals)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        # The copy is for the next period: move its shifts along with it.
        for roster, vals in zip(self, vals_list):
            if default and 'date_start' in default:
                continue
            next_start = roster.date_end + timedelta(days=1)
            vals['date_start'] = next_start
            offset = (next_start - roster.date_start).days
            next_end = period_bounds(self.env, next_start, roster.cycle or None)[1]
            vals['shift_ids'] = [
                (0, 0, dict(cmd[2], date=fields.Date.to_date(cmd[2]['date']) + timedelta(days=offset)))
                for cmd in vals.get('shift_ids', [])
                if fields.Date.to_date(cmd[2]['date']) + timedelta(days=offset) <= next_end
            ]
        return vals_list

    @api.ondelete(at_uninstall=False)
    def _unlink_except_published(self):
        if any(roster.state == 'published' for roster in self) and not self._is_admin():
            raise UserError(_('Unpublish the roster before deleting it.'))

    def _days(self):
        self.ensure_one()
        return [self.date_start + timedelta(days=n) for n in range((self.date_end - self.date_start).days + 1)]

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _is_admin(self):
        return self.env.user.has_group('advanced_rostering.group_rostering_admin')

    def _check_can_edit(self):
        for roster in self:
            if not roster.can_edit:
                raise AccessError(_('You are not allowed to change the %(state)s roster %(roster)s.',
                                    state=dict(self._fields['state'].selection)[roster.state].lower(),
                                    roster=roster.display_name))

    def action_publish(self):
        if not self.env.user.has_group('advanced_rostering.group_roster_publish'):
            raise AccessError(_('You are not allowed to publish rosters.'))
        for roster in self:
            if roster.state != 'draft':
                raise UserError(_('%s is already published.', roster.display_name))
        self.sudo().write({
            'state': 'published',
            'published_date': fields.Datetime.now(),
            'published_by_id': self.env.uid,
        })
        for roster in self:
            roster.message_post(body=_('Roster published.'))
            roster._notify_published()
        return True

    def action_unpublish(self):
        if not self.env.user.has_group('advanced_rostering.group_roster_unpublish'):
            raise AccessError(_('You are not allowed to unpublish rosters.'))
        for roster in self:
            if roster.state != 'published':
                raise UserError(_('%s is not published.', roster.display_name))
        self.sudo().write({'state': 'draft', 'published_date': False, 'published_by_id': False})
        for roster in self:
            roster.message_post(body=_('Roster unpublished for changes. The people on it no longer see it '
                                       'until it is published again.'))
        return True

    def _notify_published(self):
        """Tell the people on the roster that it is out (Settings › Rostering)."""
        self.ensure_one()
        if self.env['ir.config_parameter'].sudo().get_param('advanced_rostering.notify_publish') != 'True':
            return
        partners = self.sudo().shift_ids.user_id.partner_id
        if not partners:
            return
        self.sudo().message_notify(
            partner_ids=partners.ids,
            subject=_('Roster published: %s', self.display_name),
            body=Markup('<p>%s</p>') % _(
                'The roster %s has been published. Open Rostering › My Roster and Leave to see your shifts.',
                self.display_name),
        )

    def action_open_apply_template(self):
        self.ensure_one()
        self._check_can_edit()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apply Roster Template'),
            'res_model': 'rostering.apply.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_roster_id': self.id},
        }

    def _apply_template(self, template, replace=False):
        """Add the template's shifts to every day of the roster. Week 1 of the
        template is the first 7 days of the roster; a template with fewer weeks
        than the roster repeats."""
        self.ensure_one()
        self._check_can_edit()
        weeks = CYCLE_WEEKS.get(template.cycle, 1)
        lines_by_day = template.line_ids.grouped(lambda line: (line.week, int(line.weekday)))
        vals_list = []
        for day in self._days():
            week = (day - self.date_start).days // 7 % weeks + 1
            for line in lines_by_day.get((week, day.weekday()), []):
                vals_list.append(line._prepare_shift_vals(self, day))
        if replace:
            self.shift_ids.unlink()
        shifts = self.env['rostering.shift'].create(vals_list)
        self.message_post(body=_('%(count)s shifts added from the roster template %(template)s.',
                                 count=len(shifts), template=template.name))
        return shifts

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _action_shifts(self, view_mode):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_rostering.action_rostering_shift')
        action.update({
            'name': self.display_name,
            'domain': [('roster_id', '=', self.id)],
            'context': {
                'default_roster_id': self.id,
                'default_date': fields.Date.to_string(self.date_start),
                'initial_date': fields.Date.to_string(self.date_start),
                'search_default_group_person': 1 if view_mode == 'list' else 0,
            },
            'view_mode': view_mode,
            'views': [(False, mode) for mode in view_mode.split(',')],
        })
        return action

    def action_view_shifts(self):
        return self._action_shifts('list,calendar,pivot')

    def action_view_calendar(self):
        return self._action_shifts('calendar,list,pivot')

    def action_view_grid(self):
        action = self._action_shifts('pivot,list,calendar')
        action['context'].update({
            'pivot_row_groupby': ['person_name'],
            'pivot_column_groupby': ['date:day'],
            'pivot_measures': ['paid_hours'],
        })
        return action

    def action_view_conflicts(self):
        action = self._action_shifts('list,calendar')
        action['domain'] = [('id', 'in', self.shift_ids.filtered('on_leave').ids)]
        return action
