import logging
import re
import math
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HelpArticle(models.Model):
    _name = 'help.article'
    _description = 'Help Centre Article'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Core fields ────────────────────────────────────────────────────────────

    name = fields.Char(
        'Title', required=True, translate=True,
        tracking=True,
    )
    slug = fields.Char(
        'URL Slug',
        compute='_compute_slug', store=True, readonly=False, copy=False,
        help='Used in the /help/article/<slug> URL. Must be unique.',
    )
    summary = fields.Text(
        'Summary', translate=True,
        help='Short description shown in listings and the KC Bot search results.',
    )
    content = fields.Html(
        'Content', translate=True, sanitize=False,
        help='Full HTML article content. Use the toolbar above to format or click "Generate with AI".',
    )

    # ── Organisation ───────────────────────────────────────────────────────────

    category_id = fields.Many2one(
        'help.category', 'Category',
        ondelete='set null', index=True, tracking=True,
    )
    tag_ids = fields.Many2many('help.tag', string='Tags')
    module_ids = fields.Many2many(
        'ir.module.module', string='Related Odoo Modules',
        domain=[('state', '=', 'installed')],
        help='Tag this article with the Odoo modules it covers. The KC Bot uses this to surface contextually relevant articles.',
    )
    sequence = fields.Integer('Sequence', default=10)
    is_featured = fields.Boolean(
        'Featured',
        help='Featured articles are shown at the top of the Help Centre home tab.',
    )

    # ── Audience & state ───────────────────────────────────────────────────────

    audience = fields.Selection([
        ('internal', 'Internal Only'),
        ('external', 'External / Public'),
        ('both', 'Both (Internal & External)'),
    ], default='internal', required=True, tracking=True,
        help='Internal: visible only to authenticated Odoo users.\n'
             'External / Public: visible on the public website without login.\n'
             'Both: visible in both contexts.')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
    ], default='draft', required=True, tracking=True)

    is_public = fields.Boolean(
        'Publicly Accessible',
        compute='_compute_is_public', store=True,
        help='True when the article is Published and audience includes External.',
    )

    # ── Metadata ───────────────────────────────────────────────────────────────

    author_id = fields.Many2one(
        'res.users', 'Author',
        default=lambda self: self.env.user,
        tracking=True,
    )
    website_url = fields.Char('Website URL', compute='_compute_website_url')
    read_time_minutes = fields.Integer(
        'Estimated Read Time (min)',
        compute='_compute_read_time', store=True,
    )

    # ── Engagement ─────────────────────────────────────────────────────────────

    view_count = fields.Integer('Views', default=0, readonly=True)
    helpful_count = fields.Integer('👍 Helpful', default=0, readonly=True)
    not_helpful_count = fields.Integer('👎 Not Helpful', default=0, readonly=True)

    # ── Publishing schedule ─────────────────────────────────────────────────────

    publish_date = fields.Datetime(
        'Scheduled Publish Date',
        copy=False,
        index=True,
        tracking=True,
        help='When set, the article will be automatically published at this date/time by the hourly cron.',
    )

    # ── AI ─────────────────────────────────────────────────────────────────────

    ai_generated = fields.Boolean('AI Generated', readonly=True)
    ai_prompt = fields.Text('AI Prompt Used', readonly=True)

    # ── Constraints ────────────────────────────────────────────────────────────

    _slug_unique = models.Constraint(
        'unique(slug)',
        'Article URL slug must be unique.',
    )

    # ── Computes ───────────────────────────────────────────────────────────────

    @api.depends('name')
    def _compute_slug(self):
        for rec in self:
            if rec.name and not rec.slug:
                base = rec.name.lower()
                base = re.sub(r'[^\w\s-]', '', base)
                base = re.sub(r'[\s_-]+', '-', base).strip('-')
                slug = base
                counter = 1
                while self.search([('slug', '=', slug), ('id', '!=', rec.id or 0)], limit=1):
                    slug = f'{base}-{counter}'
                    counter += 1
                rec.slug = slug

    @api.depends('state', 'audience')
    def _compute_is_public(self):
        for rec in self:
            rec.is_public = rec.state == 'published' and rec.audience in ('external', 'both')

    @api.depends('slug')
    def _compute_website_url(self):
        for rec in self:
            rec.website_url = f'/help/article/{rec.slug}' if rec.slug else '#'

    @api.depends('content')
    def _compute_read_time(self):
        """Average reading speed ~200 words/min."""
        for rec in self:
            if rec.content:
                text = re.sub(r'<[^>]+>', ' ', rec.content or '')
                words = len(text.split())
                rec.read_time_minutes = max(1, math.ceil(words / 200))
            else:
                rec.read_time_minutes = 1

    # ── Actions ────────────────────────────────────────────────────────────────

    def action_publish(self):
        if len(self) == 1:
            # Single-record: keep strict validation with clear error messages.
            if not self.content:
                raise UserError(_('Cannot publish an article with no content.'))
            if not self.slug:
                raise UserError(_('Cannot publish an article with no URL slug.'))
            self.write({'state': 'published', 'publish_date': False})
        else:
            # Bulk: skip articles that aren't ready; report how many were skipped.
            ready = self.filtered(lambda a: a.content and a.slug)
            skipped = len(self) - len(ready)
            ready.write({'state': 'published', 'publish_date': False})
            if skipped:
                raise UserError(
                    _(
                        '%(count)s article(s) were skipped because they have no content '
                        'or no URL slug. %(published)s article(s) published successfully.',
                        count=skipped,
                        published=len(ready),
                    )
                )

    def action_unpublish(self):
        self.write({'state': 'draft'})

    def action_open_schedule_publish_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Schedule Publish'),
            'res_model': 'help.schedule.publish.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_article_id': self.id},
        }

    @api.model
    def cron_scheduled_publish(self):
        """Publish draft articles whose scheduled publish date has arrived (cron entry-point)."""
        self._do_scheduled_publish()

    def _do_scheduled_publish(self):
        """
        Core scheduled-publish logic.
        Finds all draft articles whose publish_date has passed, splits them
        into ready (has content + slug) and skipped, publishes the ready ones,
        and returns a result dict used by both the cron and the manual trigger.
        """
        now = fields.Datetime.now()
        due = self.env['help.article'].search([
            ('state', '=', 'draft'),
            ('publish_date', '!=', False),
            ('publish_date', '<=', now),
        ])
        to_publish = due.filtered(lambda a: a.content and a.slug)
        skipped    = due - to_publish

        if to_publish:
            to_publish.write({'state': 'published', 'publish_date': False})
            _logger.info('Help Centre: Auto-published %s article(s) on schedule.', len(to_publish))

        for art in skipped:
            _logger.warning(
                'Help Centre: Scheduled publish skipped article "%s" (id=%s) — '
                'missing content or URL slug.',
                art.name, art.id,
            )

        return {
            'published': [
                {
                    'id': a.id,
                    'name': a.name,
                    'website_url': f'/help/article/{a.slug}',
                    'category': a.category_id.name or '',
                }
                for a in to_publish
            ],
            'skipped': len(skipped),
        }

    def run_scheduled_publish_now(self):
        """
        Public ORM-callable entry-point for the list-view button.
        Enforces manager group, then delegates to _do_scheduled_publish().
        """
        if not self.env.user.has_group('help_centre.group_help_centre_manager'):
            raise UserError(_('You must be a Help Centre Manager to run scheduled publish.'))
        return self._do_scheduled_publish()

    def action_run_scheduled_publish(self):
        """Return the client action that opens the Scheduled Publish progress dialog."""
        return {
            'type': 'ir.actions.client',
            'tag': 'help_centre.run_scheduled_publish',
            'name': _('Run Scheduled Publish'),
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }

    def action_run_generate_articles(self):
        """Return the client action that opens the Generate Missing Articles progress dialog."""
        return {
            'type': 'ir.actions.client',
            'tag': 'help_centre.run_generate_articles',
            'name': _('Generate Missing Articles'),
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }

    def action_open_website(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.website_url,
            'target': 'new',
        }

    def action_open_generate_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Article with AI'),
            'res_model': 'help.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_article_id': self.id,
                'default_audience': self.audience,
                'default_topic': self.name,
            },
        }

    # ── Engagement helpers (called from controller) ────────────────────────────

    def _increment_view(self):
        """Increment view counter bypassing ORM write (no tracking noise)."""
        if self.id:
            self.env.cr.execute(
                'UPDATE help_article SET view_count = view_count + 1 WHERE id = %s',
                (self.id,)
            )

    def _rate(self, helpful: bool):
        """Record a thumbs-up or thumbs-down."""
        if helpful:
            self.env.cr.execute(
                'UPDATE help_article SET helpful_count = helpful_count + 1 WHERE id = %s',
                (self.id,)
            )
        else:
            self.env.cr.execute(
                'UPDATE help_article SET not_helpful_count = not_helpful_count + 1 WHERE id = %s',
                (self.id,)
            )
