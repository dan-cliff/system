# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VideoProduction(models.Model):
    _name = 'video.production'
    _description = 'Video Production'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_planned_publish desc, sequence, id'
    _date_name = 'date_planned_publish'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Production Title',
        required=True,
        tracking=True,
    )
    reference = fields.Char(
        string='Reference',
        readonly=True,
        default='New',
        copy=False,
        tracking=True,
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color Index', default=0)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    # ── Stage & State ─────────────────────────────────────────────────────
    stage_id = fields.Many2one(
        'video.production.stage',
        string='Stage',
        tracking=True,
        ondelete='restrict',
        group_expand='_read_group_stage_ids',
        default=lambda self: self._default_stage(),
        copy=False,
    )
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Starred')],
        string='Priority',
        default='0',
    )
    kanban_state = fields.Selection(
        [
            ('normal', 'On Track'),
            ('blocked', 'Behind Schedule'),
            ('done', 'Ready to Publish'),
        ],
        string='Status',
        default='normal',
        tracking=True,
        copy=False,
    )

    # ── Content Details ───────────────────────────────────────────────────
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
        tracking=True,
    )
    description = fields.Html(string='Description / Brief')
    tag_ids = fields.Many2many(
        'video.production.tag',
        'video_production_tag_rel',
        'production_id',
        'tag_id',
        string='Tags',
    )

    # ── People ────────────────────────────────────────────────────────────
    producer_id = fields.Many2one(
        'res.users',
        string='Producer / Owner',
        default=lambda self: self.env.user,
        tracking=True,
        required=True,
    )
    editor_id = fields.Many2one(
        'res.users',
        string='Lead Editor',
        tracking=True,
    )
    thumbnail_artist_id = fields.Many2one(
        'res.users',
        string='Thumbnail Artist',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Client / Brand',
        help='Client or brand this production is for (if any).',
        tracking=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────
    date_planned_shoot = fields.Date(string='Planned Shoot Date', tracking=True)
    date_planned_edit = fields.Date(string='Planned Edit Date')
    date_planned_publish = fields.Date(string='Planned Publish Date', tracking=True)
    date_published = fields.Date(string='Published Date', readonly=True, copy=False)

    # ── Source Idea ───────────────────────────────────────────────────────
    idea_id = fields.Many2one(
        'video.idea',
        string='Source Idea',
        ondelete='set null',
        tracking=True,
    )

    # ── Child Records ─────────────────────────────────────────────────────
    script_ids = fields.One2many('video.script', 'production_id', string='Scripts')
    shoot_ids = fields.One2many('video.shoot', 'production_id', string='Shoots')
    edit_job_ids = fields.One2many('video.edit.job', 'production_id', string='Edit Jobs')
    review_ids = fields.One2many('video.review', 'production_id', string='Reviews')
    metadata_ids = fields.One2many('video.metadata', 'production_id', string='Metadata')

    # ── Smart Button Counts ───────────────────────────────────────────────
    script_count = fields.Integer(compute='_compute_child_counts', string='Script Count')
    shoot_count = fields.Integer(compute='_compute_child_counts', string='Shoot Count')
    edit_job_count = fields.Integer(compute='_compute_child_counts', string='Edit Job Count')
    review_count = fields.Integer(compute='_compute_child_counts', string='Review Count')

    # ── Teleprompter ──────────────────────────────────────────────────────
    approved_script_id = fields.Many2one(
        'video.script',
        compute='_compute_approved_script_id',
        string='Latest Approved Script',
        help='The highest-version approved script for this production.',
    )

    # ── Integration: Projects ─────────────────────────────────────────────
    # Stored as a char (project name / URL) when project module not installed.
    # If project module IS installed this field is extended by post-install hook.
    project_ref = fields.Char(
        string='Project Reference',
        help='Link to an external project tracker or internal project name.',
    )

    # ── Currency (company currency, used for monetary totals) ─────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
        string='Currency',
    )

    # ── Integration: Purchase Orders ──────────────────────────────────────
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'video_production_id',
        string='Purchase Orders',
    )
    purchase_count = fields.Integer(
        compute='_compute_purchase_totals',
        string='Purchase Count',
    )
    purchase_total = fields.Monetary(
        compute='_compute_purchase_totals',
        string='Purchase Total',
        currency_field='currency_id',
    )

    # ── Integration: Sales ────────────────────────────────────────────────
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        ondelete='set null',
        tracking=True,
        help='Linked sales order for this production.',
    )

    # ── Integration Visibility Flags (read from ir.config_parameter) ──────
    show_project_integration = fields.Boolean(compute='_compute_integration_flags')
    show_crm_integration = fields.Boolean(compute='_compute_integration_flags')
    show_sales_integration = fields.Boolean(compute='_compute_integration_flags')
    show_purchase_integration = fields.Boolean(compute='_compute_integration_flags')
    show_expenses_integration = fields.Boolean(compute='_compute_integration_flags')
    show_maintenance_integration = fields.Boolean(compute='_compute_integration_flags')
    show_social_integration = fields.Boolean(compute='_compute_integration_flags')
    show_timesheet_integration = fields.Boolean(compute='_compute_integration_flags')

    @api.depends_context('uid')
    def _compute_integration_flags(self):
        get = self.env['ir.config_parameter'].sudo().get_param
        show_project = get('video_production.use_project', 'False') == 'True'
        show_crm = get('video_production.use_crm', 'False') == 'True'
        show_sales = get('video_production.use_sales', 'True') == 'True'
        show_purchase = get('video_production.use_purchase', 'False') == 'True'
        show_expenses = get('video_production.use_expenses', 'False') == 'True'
        show_maintenance = get('video_production.use_maintenance', 'False') == 'True'
        show_social = get('video_production.use_social', 'False') == 'True'
        show_timesheets = get('video_production.use_timesheets', 'False') == 'True'
        for rec in self:
            rec.show_project_integration = show_project
            rec.show_crm_integration = show_crm
            rec.show_sales_integration = show_sales
            rec.show_purchase_integration = show_purchase
            rec.show_expenses_integration = show_expenses
            rec.show_maintenance_integration = show_maintenance
            rec.show_social_integration = show_social
            rec.show_timesheet_integration = show_timesheets

    # ── Computed ──────────────────────────────────────────────────────────
    @api.depends('purchase_order_ids.amount_total')
    def _compute_purchase_totals(self):
        for rec in self:
            orders = rec.purchase_order_ids
            rec.purchase_count = len(orders)
            rec.purchase_total = sum(orders.mapped('amount_total'))

    @api.depends('script_ids.state', 'script_ids.version_number')
    def _compute_approved_script_id(self):
        for rec in self:
            approved = rec.script_ids.filtered(
                lambda s: s.state == 'approved'
            ).sorted('version_number', reverse=True)
            rec.approved_script_id = approved[:1]

    @api.depends('script_ids', 'shoot_ids', 'edit_job_ids', 'review_ids')
    def _compute_child_counts(self):
        for rec in self:
            rec.script_count = len(rec.script_ids)
            rec.shoot_count = len(rec.shoot_ids)
            rec.edit_job_count = len(rec.edit_job_ids)
            rec.review_count = len(rec.review_ids)

    # ── Defaults & Group Expand ───────────────────────────────────────────
    def _default_stage(self):
        return self.env['video.production.stage'].search(
            [], order='sequence, id', limit=1
        )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order='sequence, id')

    # ── Onchange ─────────────────────────────────────────────────────────
    @api.onchange('idea_id')
    def _onchange_idea_id(self):
        """Populate the brief from the linked idea's concept when the brief is blank."""
        if self.idea_id and not self.description:
            self.description = self.idea_id.description

    # ── ORM ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = (
                    self.env['ir.sequence'].next_by_code('video.production') or 'New'
                )
        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────
    def action_mark_published(self):
        """Mark the production as published."""
        self.ensure_one()
        published_stage = self.env['video.production.stage'].search(
            [('is_published', '=', True)], order='sequence, id', limit=1
        )
        vals = {'date_published': fields.Date.today()}
        if published_stage:
            vals['stage_id'] = published_stage.id
        self.write(vals)

    def action_view_scripts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.script',
            'view_mode': 'list,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id},
            'name': _('Scripts — %s') % self.name,
        }

    def action_view_shoots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.shoot',
            'view_mode': 'calendar,list,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id},
            'name': _('Shoots — %s') % self.name,
        }

    def action_view_edit_jobs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.edit.job',
            'view_mode': 'list,kanban,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id},
            'name': _('Edit Jobs — %s') % self.name,
        }

    def action_view_reviews(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.review',
            'view_mode': 'list,kanban,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id},
            'name': _('Reviews — %s') % self.name,
        }

    def action_view_metadata(self):
        self.ensure_one()
        if self.metadata_ids:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'video.metadata',
                'res_id': self.metadata_ids[0].id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.metadata',
            'view_mode': 'form',
            'context': {'default_production_id': self.id},
        }

    def action_new_script(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.script',
            'view_mode': 'form',
            'context': {
                'default_production_id': self.id,
                'default_name': _('Script — %s') % self.name,
            },
        }

    def action_view_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('video_production_id', '=', self.id)],
            'context': {'default_video_production_id': self.id},
            'name': _('Purchase Orders — %s') % self.name,
        }

    def action_open_teleprompter(self):
        """Open the teleprompter wizard for the latest approved script."""
        self.ensure_one()
        if not self.approved_script_id:
            raise UserError(_('No approved script found for this production.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Teleprompter'),
            'res_model': 'teleprompter.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_script_id': self.approved_script_id.id},
        }

    def action_new_review(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.review',
            'view_mode': 'form',
            'context': {
                'default_production_id': self.id,
            },
        }
