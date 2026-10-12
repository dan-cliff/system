import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .social_ai import (
    PARAM_AI_ANALYSIS, ai_analysis_enabled, ai_check, ai_job_action, ai_provider_label, ai_request_json,
    plural,
)

_logger = logging.getLogger(__name__)

# Comments analysed per AI request.
AI_BATCH_SIZE = 40


class SocialComment(models.Model):
    _name = 'social.comment'
    _inherit = ['mail.thread']
    _description = 'Social Comment'
    _order = 'comment_date desc, id desc'
    _rec_name = 'author_name'

    publication_id = fields.Many2one('social.post.publication', string='Publication', required=True,
                                     ondelete='cascade', index=True)
    post_id = fields.Many2one(related='publication_id.post_id', store=True, string='Post', index=True)
    channel_id = fields.Many2one(related='publication_id.channel_id', store=True, string='Page / Channel',
                                 index=True)
    platform_id = fields.Many2one(related='publication_id.platform_id', store=True, string='Platform')
    company_id = fields.Many2one(related='publication_id.company_id', store=True, string='Company')
    parent_id = fields.Many2one('social.comment', string='Reply To', ondelete='cascade', index=True)
    child_ids = fields.One2many('social.comment', 'parent_id', string='Replies')
    external_id = fields.Char(string='Comment ID on Platform', readonly=True, index=True)
    author_name = fields.Char(string='Author', readonly=True)
    author_external_id = fields.Char(readonly=True)
    message = fields.Text(readonly=True)
    comment_date = fields.Datetime(string='Date', readonly=True)
    likes_count = fields.Integer(string='Likes', readonly=True)
    is_own = fields.Boolean(string='Our Reply', readonly=True,
                            help='Written by the Page / Channel itself (e.g. a reply sent from Odoo).')
    replied = fields.Boolean(compute='_compute_replied', store=True)
    is_hidden = fields.Boolean(string='Hidden', readonly=True, tracking=True)

    sentiment_id = fields.Many2one('social.sentiment', string='Sentiment', tracking=True)
    sentiment_color = fields.Integer(related='sentiment_id.color')
    sentiment_score = fields.Float(string='Sentiment Score', readonly=True,
                                   help='From -1 (very negative) to 1 (very positive).')
    needs_moderation = fields.Boolean(string='Needs Moderation', tracking=True, index=True,
                                      help='Flagged as possibly inappropriate - a moderator should review it.')
    moderation_reason = fields.Text(string='Why It Was Flagged')
    ai_recommended_action = fields.Text(string='Recommended Action')
    ai_suggested_reply = fields.Text(string='Suggested Reply')
    ai_analysed_date = fields.Datetime(string='Analysed On', readonly=True)
    moderated_by_id = fields.Many2one('res.users', string='Reviewed By', readonly=True, tracking=True)
    moderated_date = fields.Datetime(string='Reviewed On', readonly=True)
    can_moderate = fields.Boolean(compute='_compute_can_moderate')
    ai_analysis_available = fields.Boolean(compute='_compute_can_moderate')

    @api.depends('child_ids.is_own')
    def _compute_replied(self):
        for comment in self:
            comment.replied = any(comment.child_ids.mapped('is_own'))

    @api.depends('channel_id')
    @api.depends_context('uid')
    def _compute_can_moderate(self):
        analysis = ai_analysis_enabled(self.env)
        for comment in self:
            comment.can_moderate = comment.channel_id._user_has_level('moderate')
            comment.ai_analysis_available = analysis

    # ------------------------------------------------------------------
    @api.model
    def _import_comments(self, publication, comments):
        """Create or update comments from provider data dicts (parents before replies)."""
        existing = {c.external_id: c for c in self.search([('publication_id', '=', publication.id)])}
        new_comments = self.browse()
        for data in comments:
            vals = {
                'author_name': data.get('author_name'),
                'author_external_id': data.get('author_id'),
                'message': data.get('message'),
                'comment_date': data.get('date'),
                'likes_count': data.get('likes') or 0,
                'is_own': bool(data.get('is_own')),
            }
            if 'is_hidden' in data:
                vals['is_hidden'] = data['is_hidden']
            parent = existing.get(data.get('parent_id')) if data.get('parent_id') else None
            if parent:
                vals['parent_id'] = parent.id
            comment = existing.get(data['external_id'])
            if comment:
                if comment.message != vals['message']:
                    vals['ai_analysed_date'] = False  # edited - analyse again
                comment.write(vals)
            else:
                vals.update({'publication_id': publication.id, 'external_id': data['external_id']})
                comment = self.create(vals)
                existing[data['external_id']] = comment
                new_comments |= comment
        return new_comments

    def write(self, vals):
        if not self.env.su:
            self._check_moderate('edit comments')
        return super().write(vals)

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    def _check_moderate(self, what):
        for comment in self:
            if not (comment.channel_id._user_has_level('moderate')
                    or (what == 'reply to comments' and comment.channel_id._user_has_level('publish'))):
                comment.channel_id._check_level('moderate', what)

    def action_reply(self):
        self.ensure_one()
        self._check_moderate('reply to comments')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reply to %s' % (self.author_name or 'comment'),
            'res_model': 'social.comment.reply.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_comment_id': self.id, 'default_message': self.ai_suggested_reply or ''},
        }

    def _send_reply(self, text):
        self.ensure_one()
        self._check_moderate('reply to comments')
        if not (text or '').strip():
            raise UserError('Write a reply first.')
        provider = self.channel_id._get_provider()
        result = provider.reply_comment(self, text)
        self.sudo().create({
            'publication_id': self.publication_id.id,
            'parent_id': self.id,
            'external_id': result.get('external_id'),
            'author_name': self.channel_id.name,
            'message': text,
            'comment_date': fields.Datetime.now(),
            'is_own': True,
        })
        self.message_post(body='Replied by %s: %s' % (self.env.user.name, text))

    def action_hide(self):
        for comment in self:
            comment._check_moderate('hide comments')
            comment.channel_id._get_provider().hide_comment(comment, True)
            comment.sudo().write({'is_hidden': True})
            comment._mark_reviewed()
        return True

    def action_unhide(self):
        for comment in self:
            comment._check_moderate('show comments')
            comment.channel_id._get_provider().hide_comment(comment, False)
            comment.sudo().write({'is_hidden': False})
        return True

    def action_delete_on_platform(self):
        for comment in self:
            comment._check_moderate('delete comments')
            comment.channel_id._get_provider().delete_comment(comment)
            comment.post_id.message_post(body='Comment by %s deleted by %s: %s' % (
                comment.author_name, self.env.user.name, comment.message or ''))
        self.sudo().unlink()
        return {'type': 'ir.actions.act_window_close'}

    def action_mark_reviewed(self):
        self._check_moderate('review flagged comments')
        self._mark_reviewed()
        return True

    def _mark_reviewed(self):
        self.sudo().write({
            'needs_moderation': False,
            'moderated_by_id': self.env.user.id,
            'moderated_date': fields.Datetime.now(),
        })

    def action_flag(self):
        self._check_moderate('flag comments')
        self.sudo().write({'needs_moderation': True})
        return True

    # ------------------------------------------------------------------
    # AI analysis
    # ------------------------------------------------------------------
    def action_ai_analyse(self):
        ai_check(self.env, PARAM_AI_ANALYSIS, 'AI Analysis')
        return ai_job_action(self, 'ai_job_analyse', 'Analysing comments by AI')

    def get_ai_job_steps(self, method):
        ai = ai_provider_label(self.env)
        posts = self.post_id
        about = ('on "%s"' % posts.name) if len(posts) == 1 else ('on %s' % plural(len(posts), 'post'))
        return [
            'Collecting %s %s' % (plural(len(self), 'comment'), about),
            'Asking %s to rate the sentiment of %s, flag any needing moderation and '
            'recommend actions' % (ai, plural(len(self), 'comment')),
            'Updating the comments',
        ]

    def ai_job_analyse(self):
        ai_check(self.env, PARAM_AI_ANALYSIS, 'AI Analysis')
        analysed = self._ai_analyse()
        flagged = len(self.filtered('needs_moderation'))
        message = 'Analysed %s' % plural(analysed, 'comment')
        if flagged:
            message += ' - %d flagged for moderation' % flagged
        return {'type': 'warning' if flagged else 'success', 'message': message + '.'}

    def _ai_analyse(self):
        """Sentiment, moderation flag, recommended action and suggested reply for each comment."""
        sentiments = self.env['social.sentiment'].search([])
        if not sentiments:
            raise UserError('Add some Sentiments in Social Manager > Configuration first.')
        to_analyse = self.filtered(lambda c: c.message and not c.is_own)
        done = 0
        for start in range(0, len(to_analyse), AI_BATCH_SIZE):
            batch = to_analyse[start:start + AI_BATCH_SIZE]
            data = ai_request_json(self.env, self._ai_prompt(batch, sentiments))
            results = data.get('comments') if isinstance(data, dict) else data
            for item in results or []:
                comment = batch.filtered(lambda c: c.id == item.get('id'))
                if not comment:
                    continue
                sentiment = sentiments.filtered(
                    lambda s: (s.name or '').lower() == str(item.get('sentiment') or '').lower())[:1]
                score = item.get('score')
                comment.sudo().write({
                    'sentiment_id': sentiment.id or comment.sentiment_id.id,
                    'sentiment_score': max(-1.0, min(1.0, float(score))) if isinstance(score, (int, float)) else 0.0,
                    'needs_moderation': bool(item.get('needs_moderation')) or comment.needs_moderation,
                    'moderation_reason': item.get('moderation_reason') or comment.moderation_reason,
                    'ai_recommended_action': item.get('recommended_action') or '',
                    'ai_suggested_reply': item.get('suggested_reply') or '',
                    'ai_analysed_date': fields.Datetime.now(),
                })
                done += 1
        return done

    def _ai_prompt(self, batch, sentiments):
        payload = [{
            'id': c.id,
            'platform': c.platform_id.name,
            'page': c.channel_id.name,
            'post': (c.post_id.message or c.post_id.name or '')[:500],
            'author': c.author_name,
            'comment': c.message,
            'in_reply_to': (c.parent_id.message or '')[:300] if c.parent_id else None,
        } for c in batch]
        return (
            'You moderate the social media pages of %s. For each comment below decide its sentiment '
            '(one of: %s), a sentiment score from -1 (very negative) to 1 (very positive), whether it '
            'needs moderation (abusive, hateful, harassing, sexual, violent, spam or scam, sharing '
            'personal information, or otherwise inappropriate for a public business page) and why, '
            'the action you recommend (e.g. thank them, answer their question, escalate a complaint '
            'to customer service, hide, delete, no action), and a short, friendly reply in our '
            'brand\'s voice when a reply is appropriate (else an empty string).\n\n'
            'Comments (JSON):\n%s\n\n'
            'Respond with ONLY JSON: {"comments": [{"id": <id>, "sentiment": "...", "score": <number>, '
            '"needs_moderation": true|false, "moderation_reason": "...", "recommended_action": "...", '
            '"suggested_reply": "..."}]}'
        ) % (self.env.company.name, ', '.join(sentiments.mapped('name')), json.dumps(payload, default=str))

    @api.model
    def _cron_ai_analyse(self):
        """Analyse new comments in the background (never while a user waits)."""
        if not ai_analysis_enabled(self.env):
            return
        comments = self.search([('ai_analysed_date', '=', False), ('is_own', '=', False),
                                ('message', '!=', False)], limit=AI_BATCH_SIZE * 5)
        try:
            comments._ai_analyse()
        except UserError as exc:
            _logger.warning('Social Manager: background AI analysis failed: %s', exc)
