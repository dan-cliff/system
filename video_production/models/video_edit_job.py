# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VideoEditJob(models.Model):
    _name = 'video.edit.job'
    _description = 'Video Edit Job'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_deadline, id'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(string='Edit Job', required=True, tracking=True)
    production_id = fields.Many2one(
        'video.production',
        string='Production',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    # ── Assignment ────────────────────────────────────────────────────────
    editor_id = fields.Many2one(
        'res.users',
        string='Assigned Editor',
        required=True,
        tracking=True,
    )
    date_assigned = fields.Date(
        string='Assigned',
        default=fields.Date.today,
    )
    date_deadline = fields.Date(
        string='Deadline',
        required=True,
        tracking=True,
    )
    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
        search='_search_is_overdue',
    )

    # ── Status ────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('review', 'Pending Review'),
            ('approved', 'Approved'),
            ('done', 'Done'),
        ],
        string='Status',
        default='pending',
        tracking=True,
        copy=False,
        group_expand='_group_expand_states',
    )
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'High')],
        string='Priority',
        default='0',
    )

    # ── Brief ─────────────────────────────────────────────────────────────
    brief = fields.Html(string='Edit Brief')
    revision_notes = fields.Html(string='Revision Notes')
    delivery_format = fields.Selection(
        [
            ('4k', '4K (3840×2160)'),
            ('1080p', '1080p (1920×1080)'),
            ('720p', '720p (1280×720)'),
            ('vertical_full', 'Vertical Full (1080×1920)'),
            ('vertical_short', 'Vertical Short (1080×1920 < 60s)'),
            ('proxy', 'Proxy / Review Copy'),
        ],
        string='Delivery Format',
        default='1080p',
    )

    # ── Versions ──────────────────────────────────────────────────────────
    version_ids = fields.One2many(
        'video.edit.version',
        'edit_job_id',
        string='Edit Versions',
    )
    current_version = fields.Integer(
        string='Current Version',
        compute='_compute_current_version',
    )
    version_count = fields.Integer(
        string='Versions',
        compute='_compute_current_version',
    )

    # ── Computed ──────────────────────────────────────────────────────────
    @api.depends('version_ids.version_number')
    def _compute_current_version(self):
        for job in self:
            versions = job.version_ids
            job.version_count = len(versions)
            job.current_version = max(versions.mapped('version_number'), default=0)

    @api.depends('date_deadline', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for job in self:
            job.is_overdue = (
                job.date_deadline
                and job.date_deadline < today
                and job.state not in ('approved', 'done')
            )

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [
                ('date_deadline', '<', today),
                ('state', 'not in', ('approved', 'done')),
            ]
        return [
            '|',
            ('date_deadline', '>=', today),
            ('state', 'in', ('approved', 'done')),
        ]

    @api.model
    def _group_expand_states(self, states, domain):
        return [key for key, _val in self._fields['state'].selection]

    # ── Actions ───────────────────────────────────────────────────────────
    def action_start(self):
        self.filtered(lambda j: j.state == 'pending').write({'state': 'in_progress'})

    def action_submit_review(self):
        for job in self:
            if job.state != 'in_progress':
                raise UserError(_('Only in-progress edit jobs can be submitted for review.'))
            job.state = 'review'

    def action_approve(self):
        self.filtered(lambda j: j.state == 'review').write({'state': 'approved'})

    def action_done(self):
        self.filtered(lambda j: j.state == 'approved').write({'state': 'done'})

    def action_reset(self):
        self.write({'state': 'pending'})

    def action_add_version(self):
        self.ensure_one()
        next_ver = self.current_version + 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.edit.version',
            'view_mode': 'form',
            'context': {
                'default_edit_job_id': self.id,
                'default_version_number': next_ver,
                'default_name': _('Cut %s') % next_ver,
            },
            'target': 'new',
        }


class VideoEditVersion(models.Model):
    _name = 'video.edit.version'
    _description = 'Edit Version / Deliverable'
    _order = 'version_number desc, id'

    edit_job_id = fields.Many2one(
        'video.edit.job',
        string='Edit Job',
        required=True,
        ondelete='cascade',
    )
    version_number = fields.Integer(string='Version No.', required=True)
    name = fields.Char(string='Cut Name', required=True)
    date_submitted = fields.Datetime(
        string='Submitted',
        default=fields.Datetime.now,
    )
    submitted_by_id = fields.Many2one(
        'res.users',
        string='Submitted By',
        default=lambda self: self.env.user,
    )

    state = fields.Selection(
        [
            ('submitted', 'Submitted'),
            ('in_review', 'In Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected / Changes Requested'),
        ],
        string='Status',
        default='submitted',
    )
    file_url = fields.Char(
        string='File / Review Link',
        help='Dropbox / Google Drive / Frame.io / WeTransfer link to the edit file.',
    )
    duration_sec = fields.Integer(string='Duration (seconds)')
    duration_display = fields.Char(
        string='Duration',
        compute='_compute_duration_display',
    )
    feedback = fields.Text(string='Feedback / Revision Notes')
    notes = fields.Text(string='Editor Notes')

    @api.depends('duration_sec')
    def _compute_duration_display(self):
        for ver in self:
            s = ver.duration_sec or 0
            mins, secs = divmod(s, 60)
            ver.duration_display = f'{mins}:{secs:02d}'
