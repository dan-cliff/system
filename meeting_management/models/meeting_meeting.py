import logging
import json
import requests
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

MS_GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


class MeetingMeeting(models.Model):
    _name = 'meeting.meeting'
    _description = 'Meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'
    _rec_name = 'display_name_full'

    # ── Identity ────────────────────────────────────────────────────────────
    reference = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    name = fields.Char(
        string='Meeting Title',
        required=True,
        tracking=True,
        translate=True,
    )
    display_name_full = fields.Char(
        string='Display Name',
        compute='_compute_display_name_full',
        store=True,
    )
    template_id = fields.Many2one(
        'meeting.template',
        string='Meeting Template',
        ondelete='set null',
        tracking=True,
    )

    # ── Scheduling ──────────────────────────────────────────────────────────
    date_start = fields.Datetime(
        string='Start Date & Time',
        required=True,
        tracking=True,
        default=lambda self: fields.Datetime.now(),
    )
    date_end = fields.Datetime(
        string='End Date & Time',
        tracking=True,
    )
    duration = fields.Float(
        string='Duration (hours)',
        compute='_compute_duration',
        store=True,
        readonly=False,
    )
    location = fields.Char(string='Location', tracking=True)
    meeting_type = fields.Selection([
        ('in_person', 'In Person'),
        ('virtual', 'Virtual / Online'),
        ('hybrid', 'Hybrid'),
    ], string='Meeting Type', default='in_person', tracking=True)

    # ── State ────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False)

    # ── People ────────────────────────────────────────────────────────────────
    chairperson_id = fields.Many2one(
        'res.partner',
        string='Chairperson',
        tracking=True,
    )
    secretary_id = fields.Many2one(
        'res.partner',
        string='Secretary / Minutes Taker',
        tracking=True,
    )
    invitee_ids = fields.Many2many(
        'res.partner',
        'meeting_invitee_rel',
        'meeting_id',
        'partner_id',
        string='Invitees',
        tracking=True,
    )
    invitee_count = fields.Integer(
        string='Invitees',
        compute='_compute_invitee_count',
    )

    # ── Agenda ────────────────────────────────────────────────────────────────
    agenda_item_ids = fields.One2many(
        'meeting.agenda.item',
        'meeting_id',
        string='Agenda Items',
        copy=True,
    )
    agenda_item_count = fields.Integer(
        string='Agenda Items',
        compute='_compute_agenda_item_count',
    )

    # ── Minutes ───────────────────────────────────────────────────────────────
    minutes_item_ids = fields.One2many(
        'meeting.minutes.item',
        'meeting_id',
        string='Minutes',
        copy=False,
    )
    general_notes = fields.Html(string='General Notes / Other Business')
    minutes_approved = fields.Boolean(
        string='Minutes Approved',
        tracking=True,
    )
    minutes_approved_date = fields.Date(string='Minutes Approved Date')

    # ── Action Items ──────────────────────────────────────────────────────────
    action_item_ids = fields.One2many(
        'meeting.action.item',
        'meeting_id',
        string='Action Items',
        copy=False,
    )
    action_item_count = fields.Integer(
        string='Action Items',
        compute='_compute_action_item_count',
    )
    open_action_count = fields.Integer(
        string='Open Actions',
        compute='_compute_open_action_count',
        store=True,
    )

    # ── Previous meeting carry-over ───────────────────────────────────────────
    previous_meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Previous Meeting',
        ondelete='set null',
        copy=False,
        index=True,
    )
    previous_open_action_ids = fields.One2many(
        'meeting.action.item',
        compute='_compute_previous_open_actions',
        string='Outstanding Actions from Previous Meeting',
    )

    # ── Next Meeting ──────────────────────────────────────────────────────────
    next_meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Next Meeting',
        ondelete='set null',
        copy=False,
        readonly=True,
        index=True,
    )
    next_meeting_date = fields.Datetime(
        string='Next Meeting Date',
        related='next_meeting_id.date_start',
        store=True,
    )
    next_meeting_location = fields.Char(
        string='Next Meeting Location',
        related='next_meeting_id.location',
        store=True,
    )

    # ── Microsoft Teams / Outlook ─────────────────────────────────────────────
    teams_meeting_id = fields.Char(
        string='Teams Meeting ID',
        readonly=True,
        copy=False,
        groups='base.group_user',
    )
    teams_join_url = fields.Char(
        string='Teams Join URL',
        readonly=True,
        copy=False,
    )
    teams_online_meeting_url = fields.Char(
        string='Teams Online Meeting URL',
        readonly=True,
        copy=False,
    )
    outlook_event_id = fields.Char(
        string='Outlook Event ID',
        readonly=True,
        copy=False,
    )
    teams_scheduled = fields.Boolean(
        string='Scheduled in Teams',
        compute='_compute_teams_scheduled',
        store=True,
    )

    # ── Notifications ─────────────────────────────────────────────────────────
    notification_template_ids = fields.Many2many(
        'meeting.notification.template',
        'meeting_notif_rel',
        'meeting_id',
        'notif_template_id',
        string='Notification Templates',
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Computed fields
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends('reference', 'name')
    def _compute_display_name_full(self):
        for rec in self:
            if rec.reference and rec.reference != _('New'):
                rec.display_name_full = f'[{rec.reference}] {rec.name}'
            else:
                rec.display_name_full = rec.name or ''

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                delta = rec.date_end - rec.date_start
                rec.duration = delta.total_seconds() / 3600.0
            else:
                rec.duration = 0.0

    @api.depends('invitee_ids')
    def _compute_invitee_count(self):
        for rec in self:
            rec.invitee_count = len(rec.invitee_ids)

    @api.depends('agenda_item_ids')
    def _compute_agenda_item_count(self):
        for rec in self:
            rec.agenda_item_count = len(rec.agenda_item_ids)

    @api.depends('action_item_ids')
    def _compute_action_item_count(self):
        for rec in self:
            rec.action_item_count = len(rec.action_item_ids)

    @api.depends('action_item_ids', 'action_item_ids.state')
    def _compute_open_action_count(self):
        for rec in self:
            rec.open_action_count = len(
                rec.action_item_ids.filtered(lambda a: a.state in ('open', 'in_progress'))
            )

    @api.depends('previous_meeting_id', 'previous_meeting_id.action_item_ids',
                 'previous_meeting_id.action_item_ids.state')
    def _compute_previous_open_actions(self):
        for rec in self:
            if rec.previous_meeting_id:
                rec.previous_open_action_ids = rec.previous_meeting_id.action_item_ids.filtered(
                    lambda a: a.state in ('open', 'in_progress')
                )
            else:
                rec.previous_open_action_ids = self.env['meeting.action.item']

    @api.depends('teams_meeting_id')
    def _compute_teams_scheduled(self):
        for rec in self:
            rec.teams_scheduled = bool(rec.teams_meeting_id)

    # ─────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ─────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('meeting.meeting') or _('New')
        return super().create(vals_list)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if not self.template_id:
            return
        tmpl = self.template_id
        if tmpl.default_location and not self.location:
            self.location = tmpl.default_location
        if tmpl.default_meeting_type:
            self.meeting_type = tmpl.default_meeting_type
        if tmpl.default_chairperson_id and not self.chairperson_id:
            self.chairperson_id = tmpl.default_chairperson_id
        if tmpl.default_secretary_id and not self.secretary_id:
            self.secretary_id = tmpl.default_secretary_id
        if tmpl.default_invitee_ids:
            self.invitee_ids = tmpl.default_invitee_ids
        if tmpl.notification_template_ids:
            self.notification_template_ids = tmpl.notification_template_ids
        # Build agenda items from template
        if tmpl.agenda_item_ids:
            agenda_lines = []
            for tpl_item in tmpl.agenda_item_ids.sorted('sequence'):
                agenda_lines.append((0, 0, {
                    'sequence': tpl_item.sequence,
                    'name': tpl_item.name,
                    'description': tpl_item.description,
                    'item_type': tpl_item.item_type,
                    'duration': tpl_item.default_duration,
                    'presenter_id': tpl_item.default_presenter_id.id if tpl_item.default_presenter_id else False,
                }))
            self.agenda_item_ids = [(5, 0, 0)] + agenda_lines
        # Set end date from default duration
        if tmpl.default_duration and self.date_start and not self.date_end:
            self.date_end = self.date_start + timedelta(hours=tmpl.default_duration)

    @api.onchange('date_start', 'duration')
    def _onchange_date_start_duration(self):
        if self.date_start and self.duration:
            self.date_end = self.date_start + timedelta(hours=self.duration)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(_('End date must be after start date.'))

    # ─────────────────────────────────────────────────────────────────────────
    # State machine actions
    # ─────────────────────────────────────────────────────────────────────────

    def action_schedule(self):
        self.write({'state': 'scheduled'})
        self._send_notifications_for_trigger('on_invite')

    def action_start(self):
        self.write({'state': 'in_progress'})
        self._send_notifications_for_trigger('on_start')

    def action_complete(self):
        for rec in self:
            rec.state = 'completed'
            rec._send_notifications_for_trigger('after_meeting')
            # Auto-schedule next meeting if template says so
            if rec.template_id and rec.template_id.auto_schedule and not rec.next_meeting_id:
                rec._create_next_meeting()

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_approve_minutes(self):
        self.write({
            'minutes_approved': True,
            'minutes_approved_date': fields.Date.today(),
        })
        self._send_notifications_for_trigger('minutes_ready')

    # ─────────────────────────────────────────────────────────────────────────
    # Notification helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _send_notifications_for_trigger(self, trigger):
        for rec in self:
            templates = rec.notification_template_ids.filtered(
                lambda t: t.trigger == trigger
            )
            for tmpl in templates:
                try:
                    tmpl.action_send_for_meeting(rec)
                except Exception as e:
                    _logger.error(
                        'Failed to send notification "%s" for meeting %s: %s',
                        tmpl.name, rec.reference, e
                    )

    def action_send_notification(self):
        """Wizard-like: open a dialog to pick a notification template and send."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Notification'),
            'res_model': 'meeting.send.notification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_meeting_id': self.id},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Microsoft Teams / Outlook integration
    # ─────────────────────────────────────────────────────────────────────────

    def _get_ms_access_token(self):
        """Return a valid Microsoft access token, refreshing if necessary."""
        ICP = self.env['ir.config_parameter'].sudo()
        access_token = ICP.get_param('meeting_management.ms_access_token', '')
        refresh_token = ICP.get_param('meeting_management.ms_refresh_token', '')
        expiry_str = ICP.get_param('meeting_management.ms_token_expiry', '')

        if access_token and expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if datetime.utcnow() < expiry - timedelta(minutes=5):
                    return access_token
            except ValueError:
                pass

        if not refresh_token:
            raise UserError(_(
                'Microsoft account not connected. Please go to Settings → Meeting Management '
                'and connect your Microsoft account.'
            ))

        # Refresh the token
        client_id = ICP.get_param('meeting_management.ms_client_id', '')
        client_secret = ICP.get_param('meeting_management.ms_client_secret', '')
        tenant_id = ICP.get_param('meeting_management.ms_tenant_id', 'common')
        token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
            'scope': 'OnlineMeetings.ReadWrite Calendars.ReadWrite',
        }
        try:
            resp = requests.post(token_url, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise UserError(_('Failed to refresh Microsoft token: %s') % str(e))

        new_access = data.get('access_token', '')
        new_refresh = data.get('refresh_token', refresh_token)
        expires_in = data.get('expires_in', 3600)
        new_expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        ICP.set_param('meeting_management.ms_access_token', new_access)
        ICP.set_param('meeting_management.ms_refresh_token', new_refresh)
        ICP.set_param('meeting_management.ms_token_expiry', new_expiry)
        return new_access

    def action_schedule_teams_meeting(self):
        """Create an online Teams meeting via Microsoft Graph API."""
        self.ensure_one()
        if self.teams_meeting_id:
            raise UserError(_('A Teams meeting has already been created for this record.'))

        token = self._get_ms_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        # Create Teams online meeting
        start_iso = self.date_start.strftime('%Y-%m-%dT%H:%M:%S')
        end_iso = (self.date_end or self.date_start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')

        meeting_payload = {
            'subject': self.name,
            'startDateTime': f'{start_iso}Z',
            'endDateTime': f'{end_iso}Z',
        }
        try:
            resp = requests.post(
                f'{MS_GRAPH_BASE}/me/onlineMeetings',
                headers=headers,
                json=meeting_payload,
                timeout=20,
            )
            resp.raise_for_status()
            meeting_data = resp.json()
        except Exception as e:
            raise UserError(_('Failed to create Teams meeting: %s') % str(e))

        self.write({
            'teams_meeting_id': meeting_data.get('id', ''),
            'teams_join_url': meeting_data.get('joinWebUrl', ''),
            'teams_online_meeting_url': meeting_data.get('onlineMeetingUrl', ''),
        })

        # Also create an Outlook calendar event
        self._create_outlook_event(token, start_iso, end_iso, meeting_data.get('joinWebUrl', ''))

        self.message_post(
            body=_('Teams meeting created. <a href="%s">Join Teams Meeting</a>') % self.teams_join_url,
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Teams Meeting Created'),
                'message': _('The Teams meeting has been created successfully.'),
                'type': 'success',
            },
        }

    def _create_outlook_event(self, token, start_iso, end_iso, join_url):
        """Create a corresponding Outlook calendar event."""
        self.ensure_one()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        attendees = []
        for partner in self.invitee_ids:
            if partner.email:
                attendees.append({
                    'emailAddress': {'address': partner.email, 'name': partner.name},
                    'type': 'required',
                })
        body_content = f'<p>Join Teams Meeting: <a href="{join_url}">{join_url}</a></p>'
        if self.general_notes:
            body_content += str(self.general_notes)

        event_payload = {
            'subject': self.name,
            'start': {'dateTime': f'{start_iso}', 'timeZone': 'UTC'},
            'end': {'dateTime': f'{end_iso}', 'timeZone': 'UTC'},
            'location': {'displayName': self.location or ''},
            'body': {'contentType': 'html', 'content': body_content},
            'attendees': attendees,
            'isOnlineMeeting': True,
            'onlineMeetingProvider': 'teamsForBusiness',
        }
        try:
            resp = requests.post(
                f'{MS_GRAPH_BASE}/me/events',
                headers=headers,
                json=event_payload,
                timeout=20,
            )
            resp.raise_for_status()
            event_data = resp.json()
            self.outlook_event_id = event_data.get('id', '')
        except Exception as e:
            _logger.warning('Failed to create Outlook event: %s', e)

    def action_update_teams_meeting(self):
        """Update the Teams meeting and Outlook event with current meeting details."""
        self.ensure_one()
        if not self.teams_meeting_id:
            raise UserError(_('No Teams meeting linked to this record.'))

        token = self._get_ms_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        start_iso = self.date_start.strftime('%Y-%m-%dT%H:%M:%S')
        end_iso = (self.date_end or self.date_start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')

        patch_payload = {
            'subject': self.name,
            'startDateTime': f'{start_iso}Z',
            'endDateTime': f'{end_iso}Z',
        }
        try:
            resp = requests.patch(
                f'{MS_GRAPH_BASE}/me/onlineMeetings/{self.teams_meeting_id}',
                headers=headers,
                json=patch_payload,
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as e:
            raise UserError(_('Failed to update Teams meeting: %s') % str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Teams Meeting Updated'),
                'message': _('The Teams meeting details have been updated.'),
                'type': 'success',
            },
        }

    def action_open_teams_meeting(self):
        """Open the Teams meeting join URL in a new tab."""
        self.ensure_one()
        if not self.teams_join_url:
            raise UserError(_('No Teams join URL available for this meeting.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.teams_join_url,
            'target': 'new',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Auto-scheduling next meeting
    # ─────────────────────────────────────────────────────────────────────────

    def _create_next_meeting(self):
        """Create the next meeting in the series from the template recurrence settings."""
        self.ensure_one()
        tmpl = self.template_id
        if not tmpl or not tmpl.auto_schedule:
            return False

        next_date = tmpl._compute_next_date(self.date_start)
        duration_hours = tmpl.default_duration or (
            (self.date_end - self.date_start).total_seconds() / 3600.0
            if self.date_end else 1.0
        )
        next_end = next_date + timedelta(hours=duration_hours)

        next_meeting = self.copy({
            'name': self.name,
            'reference': self.env['ir.sequence'].next_by_code('meeting.meeting') or _('New'),
            'date_start': next_date,
            'date_end': next_end,
            'state': 'draft',
            'template_id': tmpl.id,
            'previous_meeting_id': self.id,
            'minutes_approved': False,
            'minutes_approved_date': False,
            'teams_meeting_id': False,
            'teams_join_url': False,
            'teams_online_meeting_url': False,
            'outlook_event_id': False,
            'next_meeting_id': False,
            'minutes_item_ids': [],
            'action_item_ids': [],
        })
        self.next_meeting_id = next_meeting.id
        self.message_post(
            body=_('Next meeting automatically scheduled: <a href="/odoo/meeting-management/%s">%s</a> on %s') % (
                next_meeting.id,
                next_meeting.display_name_full,
                next_date.strftime('%d %B %Y %H:%M'),
            ),
            subtype_xmlid='mail.mt_note',
        )
        return next_meeting

    def action_schedule_next_meeting(self):
        """Manually trigger creation of the next meeting in the series."""
        self.ensure_one()
        if self.next_meeting_id:
            raise UserError(_('A next meeting is already scheduled.'))
        if not self.template_id:
            raise UserError(_('A meeting template with auto-schedule settings is required.'))
        next_meeting = self._create_next_meeting()
        if next_meeting:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'meeting.meeting',
                'res_id': next_meeting.id,
                'view_mode': 'form',
            }

    # ─────────────────────────────────────────────────────────────────────────
    # PDF report actions
    # ─────────────────────────────────────────────────────────────────────────

    def action_print_agenda(self):
        return self.env.ref('meeting_management.report_meeting_agenda').report_action(self)

    def action_print_minutes(self):
        return self.env.ref('meeting_management.report_meeting_minutes').report_action(self)

    # ─────────────────────────────────────────────────────────────────────────
    # Populate minutes from agenda
    # ─────────────────────────────────────────────────────────────────────────

    def action_populate_minutes_from_agenda(self):
        """Create a minutes entry for each agenda item that doesn't have one yet."""
        self.ensure_one()
        existing_agenda_ids = set(self.minutes_item_ids.mapped('agenda_item_id').ids)
        created = 0
        for item in self.agenda_item_ids.sorted('sequence'):
            if item.id not in existing_agenda_ids:
                self.env['meeting.minutes.item'].create({
                    'meeting_id': self.id,
                    'agenda_item_id': item.id,
                    'name': item.name,
                    'sequence': item.sequence,
                })
                created += 1
        if created:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Minutes Populated'),
                    'message': _('%d minutes item(s) created from agenda.') % created,
                    'type': 'success',
                },
            }
