# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError


class VideoReview(models.Model):
    _name = 'video.review'
    _description = 'Video Review & Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'deadline, id'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(string='Review Name', required=True, tracking=True)
    production_id = fields.Many2one(
        'video.production',
        string='Production',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    review_type = fields.Selection(
        [
            ('script', 'Script'),
            ('rough_cut', 'Rough Cut'),
            ('final_cut', 'Final Cut'),
            ('thumbnail', 'Thumbnail'),
            ('metadata', 'Metadata / SEO'),
            ('general', 'General'),
        ],
        string='Review Type',
        default='general',
        tracking=True,
    )

    # ── Status ────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_review', 'In Review'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='pending',
        tracking=True,
        copy=False,
        group_expand='_group_expand_states',
    )
    request_owner_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── Approvers ─────────────────────────────────────────────────────────
    approver_ids = fields.One2many(
        'video.review.approver',
        'review_id',
        string='Approvers',
    )
    approved_count = fields.Integer(
        string='Approved',
        compute='_compute_approval_progress',
    )
    required_count = fields.Integer(
        string='Required Approvals',
        compute='_compute_approval_progress',
    )
    all_approved = fields.Boolean(
        string='All Approved',
        compute='_compute_approval_progress',
    )

    # ── Content ───────────────────────────────────────────────────────────
    description = fields.Html(string='Review Description / Instructions')
    deadline = fields.Date(string='Deadline', tracking=True)
    reference_url = fields.Char(
        string='File / Review Link',
        help='URL to the asset being reviewed (Drive, Frame.io, Dropbox, etc.).',
    )

    # ── Linked Records ────────────────────────────────────────────────────
    script_id = fields.Many2one(
        'video.script',
        string='Script',
        domain="[('production_id', '=', production_id)]",
        ondelete='set null',
    )
    edit_version_id = fields.Many2one(
        'video.edit.version',
        string='Edit Version',
        domain="[('edit_job_id.production_id', '=', production_id)]",
        ondelete='set null',
    )

    # ── Computed ──────────────────────────────────────────────────────────
    @api.depends('approver_ids.status', 'approver_ids.required')
    def _compute_approval_progress(self):
        for review in self:
            required = review.approver_ids.filtered('required')
            approved = required.filtered(lambda a: a.status == 'approved')
            review.required_count = len(required)
            review.approved_count = len(approved)
            review.all_approved = len(required) > 0 and len(approved) == len(required)

    @api.model
    def _group_expand_states(self, states, domain):
        return [key for key, _val in self._fields['state'].selection]

    # ── Actions ───────────────────────────────────────────────────────────
    def action_submit(self):
        """Submit review for approvers to act on."""
        for review in self:
            if review.state != 'pending':
                raise UserError(_('Only pending reviews can be submitted.'))
            if not review.approver_ids:
                raise UserError(_('Please add at least one approver before submitting.'))
            review.state = 'in_review'
            for approver in review.approver_ids:
                review.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=approver.user_id.id,
                    note=_('Please review and approve: %s') % review.name,
                    date_deadline=review.deadline,
                )

    def action_approve(self):
        """Current user approves (must be listed as an approver)."""
        for review in self:
            approver = review.approver_ids.filtered(
                lambda a: a.user_id == self.env.user
            )
            if not approver and not self.env.user.has_group(
                'video_production.group_video_production_manager'
            ):
                raise AccessError(
                    _('You are not listed as an approver for this review.')
                )
            approver.write({
                'status': 'approved',
                'date_acted': fields.Datetime.now(),
            })
            if review.all_approved:
                review.state = 'approved'

    def action_refuse(self):
        """Current user refuses (must be listed as an approver or be manager)."""
        for review in self:
            approver = review.approver_ids.filtered(
                lambda a: a.user_id == self.env.user
            )
            if not approver and not self.env.user.has_group(
                'video_production.group_video_production_manager'
            ):
                raise AccessError(
                    _('You are not listed as an approver for this review.')
                )
            approver.write({
                'status': 'refused',
                'date_acted': fields.Datetime.now(),
            })
            review.state = 'refused'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_pending(self):
        for review in self:
            review.approver_ids.write({'status': 'pending', 'date_acted': False})
            review.state = 'pending'


class VideoReviewApprover(models.Model):
    _name = 'video.review.approver'
    _description = 'Review Approver'
    _order = 'sequence, id'

    review_id = fields.Many2one(
        'video.review',
        string='Review',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
    )
    required = fields.Boolean(
        string='Required',
        default=True,
        help='If checked, this approver must approve before the review is fully approved.',
    )
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
        ],
        string='Status',
        default='pending',
    )
    date_acted = fields.Datetime(string='Acted On', readonly=True)
    comment = fields.Text(string='Comment / Feedback')
