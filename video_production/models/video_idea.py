# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VideoIdea(models.Model):
    _name = 'video.idea'
    _description = 'Video Content Idea'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Concept / Title',
        required=True,
        tracking=True,
    )
    reference = fields.Char(
        string='Reference',
        readonly=True,
        default='New',
        copy=False,
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color Index', default=0)

    # ── Pipeline ──────────────────────────────────────────────────────────
    stage_id = fields.Many2one(
        'video.idea.stage',
        string='Stage',
        tracking=True,
        ondelete='restrict',
        group_expand='_read_group_stage_ids',
        default=lambda self: self._default_stage(),
    )
    kanban_state = fields.Selection(
        [
            ('normal', 'In Progress'),
            ('blocked', 'Blocked'),
            ('done', 'Ready to Promote'),
        ],
        string='Status',
        default='normal',
        tracking=True,
        copy=False,
    )

    # ── Content Details ───────────────────────────────────────────────────
    description = fields.Html(string='Concept Description')
    niche = fields.Char(string='Topic / Niche')
    target_audience = fields.Text(string='Target Audience')
    keywords = fields.Text(string='SEO Keywords', help='One keyword or phrase per line.')
    estimated_duration_min = fields.Integer(
        string='Est. Duration (min)',
        help='Estimated video length in minutes.',
    )
    video_type = fields.Selection(
        [
            ('tutorial', 'Tutorial'),
            ('review', 'Review'),
            ('vlog', 'Vlog'),
            ('short', 'Short / Reel'),
            ('livestream', 'Live Stream'),
            ('documentary', 'Documentary'),
            ('other', 'Other'),
        ],
        string='Content Type',
        default='tutorial',
    )

    # ── People ────────────────────────────────────────────────────────────
    author_id = fields.Many2one(
        'res.users',
        string='Proposed By',
        default=lambda self: self.env.user,
        tracking=True,
    )
    tag_ids = fields.Many2many(
        'video.idea.tag',
        'video_idea_tag_rel',
        'idea_id',
        'tag_id',
        string='Tags',
    )

    # ── Promotion ─────────────────────────────────────────────────────────
    production_id = fields.Many2one(
        'video.production',
        string='Linked Production',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    date_promoted = fields.Date(string='Promoted On', readonly=True, copy=False)

    # ── Computed ──────────────────────────────────────────────────────────
    production_count = fields.Integer(
        string='Productions',
        compute='_compute_production_count',
    )

    @api.depends('production_id')
    def _compute_production_count(self):
        for idea in self:
            idea.production_count = 1 if idea.production_id else 0

    # ── Defaults & Group Expand ───────────────────────────────────────────
    def _default_stage(self):
        return self.env['video.idea.stage'].search([], order='sequence, id', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order='sequence, id')

    # ── ORM ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = (
                    self.env['ir.sequence'].next_by_code('video.idea') or 'New'
                )
        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────
    def action_promote_to_production(self):
        """Create a new Video Production from this idea."""
        self.ensure_one()
        if self.production_id:
            raise UserError(
                _('This idea is already linked to production "%s".') % self.production_id.name
            )
        production = self.env['video.production'].create({
            'name': self.name,
            'idea_id': self.id,
            'video_type': self.video_type,
            'description': self.description,
        })
        self.write({
            'production_id': production.id,
            'date_promoted': fields.Date.today(),
        })
        # Move to the dedicated "Complete" stage to signal the idea has been
        # converted to a production.  Look up by XMLID so this is not confused
        # with the "Approved" stage that precedes promotion.
        complete_stage = self.env.ref(
            'video_production.video_idea_stage_complete', raise_if_not_found=False
        )
        if complete_stage:
            self.stage_id = complete_stage
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.production',
            'res_id': production.id,
            'view_mode': 'form',
        }

    def action_view_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.production',
            'res_id': self.production_id.id,
            'view_mode': 'form',
        }

    def action_open_ai_idea_wizard(self):
        """Open the AI content idea generation wizard."""
        return {
            'name': _('Generate Content Ideas with AI'),
            'type': 'ir.actions.act_window',
            'res_model': 'video.idea.ai.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
