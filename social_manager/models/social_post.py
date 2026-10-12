import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .social_ai import (
    PARAM_AI_ANALYSIS, PARAM_AI_RECOMMENDATIONS, ai_check, ai_job_action, ai_provider_label,
    ai_request_json, plural,
)

_logger = logging.getLogger(__name__)

# States in which a post can still be edited as a draft.
DRAFT_STATES = ('proposed', 'draft', 'rejected', 'failed')
# Fields that only describe the post's lifecycle; writing them isn't "editing" the post.
LIFECYCLE_FIELDS = {
    'state', 'published_date', 'approved_by_id', 'approval_date', 'rejection_reason',
    'message_follower_ids', 'activity_ids', 'message_ids', 'ai_performance_rank',
    'ai_performance_note', 'ai_ranked_date',
}


class SocialPost(models.Model):
    _name = 'social.post'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Social Post'
    _order = 'id desc'

    name = fields.Char(string='Title', required=True, tracking=True,
                       help='Used as the video title on YouTube and as a reference everywhere else.')
    message = fields.Text(string='Post Content', tracking=True)
    link_url = fields.Char(string='Link')
    attachment_ids = fields.Many2many('ir.attachment', 'social_post_attachment_rel', 'post_id',
                                      'attachment_id', string='Images / Videos')
    channel_ids = fields.Many2many('social.channel', 'social_post_channel_rel', 'post_id', 'channel_id',
                                   string='Pages / Channels', tracking=True,
                                   domain="[('company_id', 'in', [company_id, False])]")
    platform_ids = fields.Many2many('social.platform', string='Platforms', compute='_compute_platform_ids')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user, tracking=True)

    # Technical workflow state that the code depends on.
    state = fields.Selection([
        ('proposed', 'Proposed'),
        ('draft', 'Draft'),
        ('pending', 'Awaiting Approval'),
        ('scheduled', 'Scheduled'),
        ('posting', 'Publishing'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
        ('dismissed', 'Dismissed'),
    ], default='draft', required=True, tracking=True, copy=False, index=True)
    scheduled_date = fields.Datetime(string='Scheduled For', tracking=True, copy=False)
    published_date = fields.Datetime(string='Published On', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approval_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    rejection_reason = fields.Text(readonly=True, copy=False)

    publication_ids = fields.One2many('social.post.publication', 'post_id', string='Publications')
    comment_ids = fields.One2many('social.comment', 'post_id', string='Comment List')
    income_ids = fields.One2many('social.income', 'post_id', string='Income Entries')

    likes_count = fields.Integer(string='Likes', compute='_compute_metrics', store=True)
    reactions_count = fields.Integer(string='Reactions', compute='_compute_metrics', store=True)
    comments_count = fields.Integer(string='Comments', compute='_compute_metrics', store=True)
    shares_count = fields.Integer(string='Shares', compute='_compute_metrics', store=True)
    views_count = fields.Integer(string='Views', compute='_compute_metrics', store=True)
    engagement_score = fields.Float(string='Engagement Score', compute='_compute_metrics', store=True,
                                    aggregator='avg')
    income_total = fields.Monetary(string='Income', compute='_compute_income', store=True)
    flagged_comment_count = fields.Integer(compute='_compute_flagged_comment_count')
    has_failed_publications = fields.Boolean(compute='_compute_has_failed_publications')
    is_monetised = fields.Boolean(compute='_compute_is_monetised')

    # AI
    is_ai_proposal = fields.Boolean(string='AI Proposal', readonly=True, copy=False)
    event_id = fields.Many2one('social.event', string='Special Event / Release', tracking=True)
    ai_rationale = fields.Text(string='Why the AI Suggests This', copy=False)
    ai_action_items = fields.Text(string='Action Items', copy=False)
    ai_suggested_date = fields.Date(string='Suggested Posting Date', copy=False)
    ai_proposed_date = fields.Datetime(string='Proposed On', readonly=True, copy=False)
    ai_performance_rank = fields.Integer(string='AI Performance Rank', readonly=True, copy=False,
                                         help='1 is the best performing post in the last AI ranking.')
    ai_performance_note = fields.Text(string='AI Performance Insight', readonly=True, copy=False)
    ai_ranked_date = fields.Datetime(string='Ranked On', readonly=True, copy=False)
    ai_analysis_available = fields.Boolean(compute='_compute_ai_flags')
    ai_recommendations_available = fields.Boolean(compute='_compute_ai_flags')

    # Which actions the current user may take, for the form's buttons.
    can_publish = fields.Boolean(compute='_compute_user_rights')
    can_approve = fields.Boolean(compute='_compute_user_rights')
    can_delete = fields.Boolean(compute='_compute_user_rights')

    @api.depends('channel_ids')
    def _compute_platform_ids(self):
        for post in self:
            post.platform_ids = post.channel_ids.platform_id

    @api.depends('publication_ids.likes_count', 'publication_ids.reactions_count',
                 'publication_ids.comments_count', 'publication_ids.shares_count',
                 'publication_ids.views_count', 'publication_ids.engagement_score')
    def _compute_metrics(self):
        for post in self:
            pubs = post.publication_ids
            post.likes_count = sum(pubs.mapped('likes_count'))
            post.reactions_count = sum(pubs.mapped('reactions_count'))
            post.comments_count = sum(pubs.mapped('comments_count'))
            post.shares_count = sum(pubs.mapped('shares_count'))
            post.views_count = sum(pubs.mapped('views_count'))
            post.engagement_score = sum(pubs.mapped('engagement_score'))

    @api.depends('income_ids.amount')
    def _compute_income(self):
        for post in self:
            post.income_total = sum(post.income_ids.mapped('amount'))

    def _compute_flagged_comment_count(self):
        for post in self:
            post.flagged_comment_count = len(post.comment_ids.filtered('needs_moderation'))

    @api.depends('publication_ids.state')
    def _compute_has_failed_publications(self):
        for post in self:
            post.has_failed_publications = 'failed' in post.publication_ids.mapped('state')

    @api.depends('channel_ids.is_monetised')
    def _compute_is_monetised(self):
        for post in self:
            post.is_monetised = any(post.channel_ids.mapped('is_monetised'))

    def _compute_ai_flags(self):
        from .social_ai import ai_analysis_enabled, ai_recommendations_enabled
        analysis = ai_analysis_enabled(self.env)
        recommendations = ai_recommendations_enabled(self.env)
        for post in self:
            post.ai_analysis_available = analysis
            post.ai_recommendations_available = recommendations

    @api.depends('channel_ids')
    @api.depends_context('uid')
    def _compute_user_rights(self):
        for post in self:
            channels = post.channel_ids
            post.can_publish = channels._user_has_level('publish') if channels else True
            post.can_approve = channels._user_has_level('approve') if channels else True
            post.can_delete = channels._user_has_level('delete') if channels else True

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def _check_edit_rights(self, channels=None):
        for post in self:
            target = channels if channels is not None else post.channel_ids
            if post.state in DRAFT_STATES or post.state == 'pending':
                if not (target._user_has_level('draft') or target._user_has_level('publish')):
                    target._check_level('draft', 'edit this post')
            else:
                target._check_level('publish', 'edit a scheduled or published post')

    def _set_state(self, state, **vals):
        """Workflow state changes go through here; direct writes of `state` are refused."""
        vals['state'] = state
        return self.with_context(social_post_workflow=True).write(vals)

    def _check_state_write(self, vals):
        if 'state' in vals and not self.env.su and not self.env.context.get('social_post_workflow'):
            raise AccessError('Use the buttons on the post to change its status.')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                if vals.get('state', 'draft') != 'draft':
                    raise AccessError('New posts start as drafts.')
        posts = super().create(vals_list)
        if not self.env.su:
            posts._check_edit_rights()
        return posts

    def write(self, vals):
        self._check_state_write(vals)
        content_change = set(vals) - LIFECYCLE_FIELDS
        if content_change and not self.env.su:
            self._check_edit_rights()
        result = super().write(vals)
        if content_change and 'channel_ids' in vals and not self.env.su:
            self._check_edit_rights()
        return result

    def unlink(self):
        if not self.env.su:
            for post in self:
                if post.state not in ('proposed', 'dismissed') or post.channel_ids:
                    post.channel_ids._check_level('delete', 'delete posts')
        return super().unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for post, vals in zip(self, vals_list):
            vals['name'] = '%s (copy)' % post.name
        return vals_list

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_ready(self):
        for post in self:
            if not post.channel_ids:
                raise UserError('Choose at least one Page / Channel for "%s".' % post.name)
            if not (post.message or post.attachment_ids or post.link_url):
                raise UserError('"%s" has nothing to post - add content, a link or an image / video.' % post.name)
            for channel in post.channel_ids:
                channel._get_provider().check_post(post, channel)

    def _approvers(self):
        """Users who can approve this post."""
        self.ensure_one()
        users = self.env['res.users']
        for channel in self.channel_ids.sudo():
            groups = channel.group_approve_id | channel.platform_id.group_approve_id
            users |= groups.all_user_ids
        users |= self.env.ref('social_manager.group_social_manager').sudo().all_user_ids
        return users.filtered(lambda u: not u.share and u.active)

    def action_submit(self):
        """Send draft posts to the approvers."""
        self._check_ready()
        for post in self:
            if post.state not in DRAFT_STATES:
                raise UserError('Only draft posts can be submitted for approval.')
            if not (post.channel_ids._user_has_level('draft') or post.channel_ids._user_has_level('publish')):
                post.channel_ids._check_level('draft', 'submit posts for approval')
            post._set_state('pending')
            approvers = post._approvers() - self.env.user
            if approvers:
                post.message_subscribe(partner_ids=approvers.partner_id.ids)
            post.message_post(
                body='Submitted for approval by %s.' % self.env.user.name,
                partner_ids=approvers.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_approve(self):
        for post in self:
            if post.state != 'pending':
                raise UserError('Only posts awaiting approval can be approved.')
            post.channel_ids._check_level('approve', 'approve posts')
            post.write({'approved_by_id': self.env.user.id, 'approval_date': fields.Datetime.now()})
            post.message_post(body='Approved by %s.' % self.env.user.name)
            post.sudo()._schedule_or_publish()
        return True

    def action_reject(self):
        self.ensure_one()
        self.channel_ids._check_level('approve', 'reject posts')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Post',
            'res_model': 'social.post.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_post_id': self.id},
        }

    def _reject(self, reason):
        self.ensure_one()
        self.channel_ids._check_level('approve', 'reject posts')
        self._set_state('rejected', rejection_reason=reason)
        self.message_post(body='Rejected by %s: %s' % (self.env.user.name, reason or ''),
                          partner_ids=self.user_id.partner_id.ids, subtype_xmlid='mail.mt_comment')

    def action_publish_now(self):
        self._check_ready()
        for post in self:
            post.channel_ids._check_level('publish', 'publish posts')
            if post.state not in DRAFT_STATES + ('pending', 'scheduled'):
                raise UserError('"%s" has already been published.' % post.name)
            post.scheduled_date = False
            post.sudo()._publish()
        return True

    def action_schedule(self):
        self._check_ready()
        for post in self:
            post.channel_ids._check_level('publish', 'schedule posts')
            if not post.scheduled_date:
                raise UserError('Set the date and time to publish "%s" first.' % post.name)
            if post.scheduled_date <= fields.Datetime.now():
                raise UserError('The scheduled date of "%s" is in the past.' % post.name)
            post._set_state('scheduled')
        return True

    def action_back_to_draft(self):
        for post in self:
            if post.state not in ('pending', 'scheduled', 'rejected', 'failed'):
                raise UserError('Only posts that are not yet published can go back to draft.')
            if post.state == 'scheduled':
                post.channel_ids._check_level('publish', 'unschedule posts')
            post._set_state('draft')
        return True

    def _schedule_or_publish(self):
        for post in self:
            if post.scheduled_date and post.scheduled_date > fields.Datetime.now():
                post._set_state('scheduled')
            else:
                post._publish()

    def _publish(self):
        """Create a publication per channel (if missing) and publish them."""
        for post in self:
            post._set_state('posting')
            Publication = self.env['social.post.publication'].sudo()
            for channel in post.channel_ids:
                publication = post.publication_ids.filtered(lambda p: p.channel_id == channel)
                if not publication:
                    publication = Publication.create({'post_id': post.id, 'channel_id': channel.id})
                if publication.state != 'posted':
                    publication._publish()
            failed = post.publication_ids.filtered(lambda p: p.state == 'failed')
            if 'posted' in post.publication_ids.mapped('state'):
                post._set_state('posted', published_date=fields.Datetime.now())
            else:
                post._set_state('failed')
            if failed:
                post.message_post(body=Markup('Publishing failed on:<ul>%s</ul>') % Markup().join(
                    Markup('<li>%s: %s</li>') % (p.channel_id.display_name, p.failure_reason or '')
                    for p in failed))

    def action_retry(self):
        self.ensure_one()
        self.channel_ids._check_level('publish', 'publish posts')
        self.sudo()._publish()
        return True

    def action_delete_from_platforms(self):
        """Delete the published posts on the platforms; the post stays in Odoo as a record."""
        for post in self:
            post.channel_ids._check_level('delete', 'delete posts')
            post.publication_ids.filtered(lambda p: p.state == 'posted')._delete_on_platform()
        return True

    def action_sync(self):
        self.publication_ids.filtered(lambda p: p.state == 'posted' and p.external_id)._sync_from_platform()
        return True

    @api.model
    def _cron_publish_scheduled(self):
        posts = self.search([('state', '=', 'scheduled'), ('scheduled_date', '<=', fields.Datetime.now())])
        for post in posts:
            try:
                with self.env.cr.savepoint():
                    post._publish()
            except Exception as exc:
                _logger.exception('Social Manager: publishing post %s failed', post.id)
                post._set_state('failed')
                post.message_post(body='Publishing failed: %s' % exc)

    # ------------------------------------------------------------------
    # AI proposals
    # ------------------------------------------------------------------
    def action_accept_proposal(self):
        """Progress an AI proposal: it becomes an ordinary draft post."""
        for post in self.filtered(lambda p: p.state in ('proposed', 'dismissed')):
            post._set_state('draft')
            post.message_post(body='AI proposal accepted by %s.' % self.env.user.name)
        return True

    def action_dismiss_proposal(self):
        for post in self.filtered(lambda p: p.state == 'proposed'):
            post._set_state('dismissed')
            post.message_post(body='AI proposal dismissed by %s.' % self.env.user.name)
        return True

    def action_ai_recommend(self):
        """Ask the AI for proposed posts now (the weekly scheduled action does the same)."""
        ai_check(self.env, PARAM_AI_RECOMMENDATIONS, 'AI Recommendations')
        return ai_job_action(self.env['social.post'], 'ai_job_recommend', 'Proposing posts by AI')

    def action_ai_rank(self):
        """Rank recently published posts by performance."""
        ai_check(self.env, PARAM_AI_ANALYSIS, 'AI Analysis')
        return ai_job_action(self.env['social.post'], 'ai_job_rank', 'Ranking post performance by AI')

    def get_ai_job_steps(self, method):
        """Steps for the AI progress overlay, worded for what the AI is about to do."""
        ai = ai_provider_label(self.env)
        if method == 'ai_job_recommend':
            events = self.env['social.event'].search(self.env['social.event']._upcoming_domain())
            best = self._best_performing_posts()
            what = 'posts for %s' % (', '.join(events.mapped('name')[:5]) or 'upcoming special days')
            return [
                'Gathering %s and the %s' % (
                    plural(len(events), 'upcoming event or release', 'upcoming events and releases'),
                    plural(len(best), 'best performing post')),
                'Asking %s to propose %s, with draft copy and action items' % (ai, what),
                'Adding the proposals to Social Manager',
            ]
        if method == 'ai_job_rank':
            count = len(self._posts_to_rank())
            return [
                'Collecting the metrics of %s' % plural(count, 'published post'),
                'Asking %s to rank %s and explain what works' % (ai, plural(count, 'post')),
                'Updating the posts\' performance ranks',
            ]
        return ['Asking %s' % ai, 'Updating the records']

    @api.model
    def _posts_to_rank(self):
        return self.search([('state', '=', 'posted')], order='published_date desc', limit=50)

    @api.model
    def _best_performing_posts(self, limit=10):
        """Best posts by AI rank (when ranked) and engagement, for the AI to build on."""
        posts = self.search([('state', '=', 'posted')], order='engagement_score desc', limit=100)
        ranked = posts.filtered('ai_performance_rank').sorted('ai_performance_rank')
        return (ranked | posts)[:limit]

    def _ai_post_summary(self):
        self.ensure_one()
        return {
            'id': self.id,
            'title': self.name,
            'content': (self.message or '')[:1500],
            'platforms': ', '.join(self.channel_ids.mapped(lambda c: '%s (%s)' % (c.name, c.platform_id.name))),
            'published': self.published_date.strftime('%d/%m/%Y %H:%M') if self.published_date else '',
            'has_media': bool(self.attachment_ids),
            'likes': self.likes_count,
            'reactions': self.reactions_count,
            'comments': self.comments_count,
            'shares': self.shares_count,
            'views': self.views_count,
            'engagement_score': round(self.engagement_score, 2),
            'income': self.income_total,
            'ai_rank': self.ai_performance_rank or None,
            'ai_insight': self.ai_performance_note or '',
        }

    def ai_job_rank(self):
        import json
        ai_check(self.env, PARAM_AI_ANALYSIS, 'AI Analysis')
        posts = self._posts_to_rank()
        if not posts:
            return {'type': 'warning', 'message': 'There are no published posts to rank yet.'}
        data = ai_request_json(self.env, (
            'You are a social media performance analyst for %s. Rank these published posts from '
            'best (1) to worst performing, weighing engagement relative to reach, comments, shares, '
            'views and income. For each post give one short sentence explaining what made it work '
            'or not (style, topic, format, timing).\n\n'
            'Posts (JSON):\n%s\n\n'
            'Respond with ONLY JSON: {"ranking": [{"id": <post id>, "rank": <1..n>, '
            '"insight": "..."}], "what_works": "2-3 sentences on the post styles that perform best"}'
        ) % (self.env.company.name, json.dumps([p._ai_post_summary() for p in posts], default=str)))
        ranking = data.get('ranking') if isinstance(data, dict) else data
        now = fields.Datetime.now()
        posts.sudo().write({'ai_performance_rank': 0})
        updated = 0
        for item in ranking or []:
            post = posts.filtered(lambda p: p.id == item.get('id'))
            if post and isinstance(item.get('rank'), int):
                post.sudo().write({
                    'ai_performance_rank': item['rank'],
                    'ai_performance_note': item.get('insight') or '',
                    'ai_ranked_date': now,
                })
                updated += 1
        if isinstance(data, dict) and data.get('what_works'):
            self.env['ir.config_parameter'].sudo().set_param('social_manager.ai_what_works', data['what_works'])
        return {'type': 'success', 'message': 'Ranked %s by performance.' % plural(updated, 'post')}

    def ai_job_recommend(self):
        ai_check(self.env, PARAM_AI_RECOMMENDATIONS, 'AI Recommendations')
        count = self._ai_generate_proposals()
        if not count:
            return {'type': 'warning', 'message': 'The AI did not propose any posts this time.'}
        return {'type': 'success', 'message': 'The AI proposed %s - see Posts > Proposed.' % plural(count, 'post')}

    @api.model
    def _cron_ai_recommendations(self):
        from .social_ai import ai_recommendations_enabled
        if not ai_recommendations_enabled(self.env):
            return
        try:
            self._ai_generate_proposals()
        except UserError as exc:
            _logger.warning('Social Manager: AI recommendations failed: %s', exc)

    @api.model
    def _ai_generate_proposals(self):
        """Send the current date, upcoming events/releases, channels and best posts to the AI and
        create a Proposed post for each suggestion."""
        import json
        today = fields.Date.context_today(self)
        Event = self.env['social.event']
        events = Event.search(Event._upcoming_domain())
        channels = self.env['social.channel'].search([('connection_state', '=', 'connected')])
        best = self._best_performing_posts()
        what_works = self.env['ir.config_parameter'].sudo().get_param('social_manager.ai_what_works') or ''
        recent_titles = self.search([('create_date', '>=', fields.Date.subtract(today, days=60))]).mapped('name')
        context = {
            'today': today.strftime('%d/%m/%Y (%A)'),
            'company': self.env.company.name,
            'country': self.env.company.country_id.name or '',
            'channels': [{'id': c.id, 'name': c.name, 'platform': c.platform_id.name,
                          'followers': c.follower_count} for c in channels],
            'upcoming_events_and_releases': [e._ai_summary() for e in events],
            'best_performing_posts': [p._ai_post_summary() for p in best],
            'what_works': what_works,
            'recent_post_titles_to_avoid_repeating': recent_titles[:50],
        }
        data = ai_request_json(self.env, (
            'You are the social media manager for %s. Using the information below, propose social '
            'media posts for the coming weeks: one for each upcoming company event or release that '
            'needs one, plus posts for relevant special days, holidays or awareness days in %s. '
            'Build on the style, format and topics of the best performing posts. For each proposal '
            'write ready-to-post draft copy suited to the chosen channels, and the action items '
            'needed to make it happen (e.g. photos to take, approvals, links to prepare).\n\n'
            'Information (JSON):\n%s\n\n'
            'Respond with ONLY JSON: {"proposals": [{"title": "...", "content": "draft post copy", '
            '"channel_ids": [ids from channels], "event_id": <id from upcoming_events_and_releases or null>, '
            '"suggested_date": "dd/mm/yyyy", "rationale": "why, and which past post style it builds on", '
            '"action_items": ["...", "..."]}]}'
        ) % (self.env.company.name, context['country'] or 'our country', json.dumps(context, default=str)))
        proposals = data.get('proposals') if isinstance(data, dict) else data
        Post = self.sudo()
        created = 0
        for item in proposals or []:
            if not isinstance(item, dict) or not item.get('title'):
                continue
            channel_ids = [cid for cid in (item.get('channel_ids') or []) if cid in channels.ids]
            event = events.filtered(lambda e: e.id == item.get('event_id'))
            suggested = False
            if item.get('suggested_date'):
                try:
                    from datetime import datetime
                    suggested = datetime.strptime(item['suggested_date'], '%d/%m/%Y').date()
                except (TypeError, ValueError):
                    suggested = False
            action_items = item.get('action_items') or []
            if isinstance(action_items, list):
                action_items = '\n'.join('- %s' % a for a in action_items)
            Post.create({
                'name': item['title'][:200],
                'message': item.get('content') or '',
                'channel_ids': [(6, 0, channel_ids)],
                'event_id': event[:1].id,
                'state': 'proposed',
                'is_ai_proposal': True,
                'ai_rationale': item.get('rationale') or '',
                'ai_action_items': action_items,
                'ai_suggested_date': suggested,
                'ai_proposed_date': fields.Datetime.now(),
                'user_id': False,
                'company_id': self.env.company.id,
            })
            created += 1
        return created

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_view_comments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_comment')
        action['domain'] = [('post_id', '=', self.id)]
        return action

    def action_view_income(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_income')
        action['domain'] = [('post_id', '=', self.id)]
        return action

    def action_ai_analyse_comments(self):
        self.ensure_one()
        ai_check(self.env, PARAM_AI_ANALYSIS, 'AI Analysis')
        comments = self.comment_ids
        if not comments:
            raise UserError('This post has no comments to analyse yet - synchronise it first.')
        return ai_job_action(comments, 'ai_job_analyse', 'Analysing comments by AI')


class SocialPostRejectWizard(models.TransientModel):
    _name = 'social.post.reject.wizard'
    _description = 'Reject Social Post'

    post_id = fields.Many2one('social.post', required=True)
    reason = fields.Text(required=True)

    def action_reject(self):
        self.post_id._reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
