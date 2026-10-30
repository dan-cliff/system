# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .rostering_tools import search_positive

# Fields of the request itself: once submitted they only change through the
# workflow (reset to draft first).
REQUEST_FIELDS = {'user_id', 'leave_type_id', 'date_from', 'date_to', 'reason'}


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
    duration_days = fields.Integer(string='Days', compute='_compute_duration_days', store=True)
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

    @api.depends('date_from', 'date_to')
    def _compute_duration_days(self):
        for leave in self:
            if leave.date_from and leave.date_to and leave.date_to >= leave.date_from:
                leave.duration_days = (leave.date_to - leave.date_from).days + 1
            else:
                leave.duration_days = 0

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
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for leave in self:
            if leave.date_to < leave.date_from:
                raise ValidationError(_('Leave cannot end before it starts.'))

    @api.constrains('date_from', 'date_to', 'state', 'user_id')
    def _check_overlap(self):
        field = self._person_field()
        for leave in self.filtered(lambda l: l.state in ('draft', 'submitted', 'approved') and l[field]):
            other = self.sudo().search([
                ('id', '!=', leave.id),
                (field, '=', leave[field].id),
                ('state', 'in', ('draft', 'submitted', 'approved')),
                ('date_from', '<=', leave.date_to),
                ('date_to', '>=', leave.date_from),
            ], limit=1)
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
