import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Weights for the engagement score: a share or comment says more than a like.
ENGAGEMENT_WEIGHTS = {'likes_count': 1, 'reactions_count': 1, 'comments_count': 3, 'shares_count': 5}


class SocialPostPublication(models.Model):
    """A post as published on one Page / Channel."""
    _name = 'social.post.publication'
    _description = 'Social Post Publication'
    _order = 'id desc'

    post_id = fields.Many2one('social.post', string='Post', required=True, ondelete='cascade', index=True)
    channel_id = fields.Many2one('social.channel', string='Page / Channel', required=True,
                                 ondelete='restrict', index=True)
    platform_id = fields.Many2one(related='channel_id.platform_id', store=True, string='Platform')
    company_id = fields.Many2one(related='post_id.company_id', store=True, string='Company')
    currency_id = fields.Many2one(related='company_id.currency_id')
    is_monetised = fields.Boolean(related='channel_id.is_monetised')
    # Technical state of this publication, set by the code.
    state = fields.Selection([
        ('pending', 'Pending'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
        ('deleted', 'Deleted'),
    ], default='pending', required=True, readonly=True, index=True)
    external_id = fields.Char(string='Post ID on Platform', readonly=True, index=True)
    external_url = fields.Char(string='Post URL', readonly=True)
    published_date = fields.Datetime(string='Published On', readonly=True)
    failure_reason = fields.Text(readonly=True)
    last_sync = fields.Datetime(string='Last Synchronised', readonly=True)

    likes_count = fields.Integer(string='Likes', readonly=True)
    reactions_count = fields.Integer(string='Reactions', readonly=True)
    comments_count = fields.Integer(string='Comments', readonly=True)
    shares_count = fields.Integer(string='Shares', readonly=True)
    views_count = fields.Integer(string='Views / Impressions', readonly=True)
    engagement_score = fields.Float(compute='_compute_engagement_score', store=True, aggregator='avg')

    comment_ids = fields.One2many('social.comment', 'publication_id', string='Comment List')
    income_ids = fields.One2many('social.income', 'publication_id', string='Income Entries')
    income_total = fields.Monetary(string='Income', compute='_compute_income_total', store=True)

    @api.depends('post_id.name', 'channel_id.name')
    def _compute_display_name(self):
        for publication in self:
            publication.display_name = '%s - %s' % (publication.post_id.name or '', publication.channel_id.name or '')

    @api.depends('likes_count', 'reactions_count', 'comments_count', 'shares_count', 'views_count')
    def _compute_engagement_score(self):
        for publication in self:
            interactions = sum(publication[field] * weight for field, weight in ENGAGEMENT_WEIGHTS.items())
            # Views barely count on their own, but keep video posts comparable.
            publication.engagement_score = interactions + publication.views_count / 100.0

    @api.depends('income_ids.amount')
    def _compute_income_total(self):
        for publication in self:
            publication.income_total = sum(publication.income_ids.mapped('amount'))

    # ------------------------------------------------------------------
    def _publish(self):
        for publication in self:
            provider = publication.channel_id._get_provider()
            try:
                result = provider.publish(publication.post_id, publication.channel_id)
            except Exception as exc:  # a failed platform must not stop the others
                _logger.warning('Social Manager: publishing to %s failed: %s',
                                publication.channel_id.display_name, exc)
                publication.write({'state': 'failed', 'failure_reason': str(exc)})
                continue
            publication.write({
                'state': 'posted',
                'external_id': result.get('external_id'),
                'external_url': result.get('url'),
                'published_date': fields.Datetime.now(),
                'failure_reason': False,
            })

    def _sync_from_platform(self):
        """Fetch metrics and comments from the platform."""
        Comment = self.env['social.comment'].sudo()
        for publication in self.sudo():
            provider = publication.channel_id._get_provider()
            try:
                metrics = provider.fetch_metrics(publication)
                if metrics:
                    publication.write(metrics)
                comments = provider.fetch_comments(publication)
            except UserError as exc:
                publication.failure_reason = str(exc)
                continue
            Comment._import_comments(publication, comments)
            publication.last_sync = fields.Datetime.now()

    def _delete_on_platform(self):
        for publication in self:
            publication.channel_id._check_level('delete', 'delete posts')
            provider = publication.channel_id._get_provider()
            provider.delete_post(publication)
            publication.sudo().state = 'deleted'
            publication.post_id.message_post(body='Deleted from %s by %s.' % (
                publication.channel_id.display_name, self.env.user.name))

    def action_sync(self):
        self.filtered(lambda p: p.state == 'posted' and p.external_id)._sync_from_platform()
        return True

    def action_open_url(self):
        self.ensure_one()
        if not self.external_url:
            raise UserError('This post has no link on the platform.')
        return {'type': 'ir.actions.act_url', 'url': self.external_url, 'target': 'new'}
