import re
import uuid
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class HelpCentreController(http.Controller):

    # ─────────────────────────────────────────────────────────────────────────
    # Website pages
    # ─────────────────────────────────────────────────────────────────────────

    @http.route('/help', type='http', auth='public', website=True)
    def index(self, **kwargs):
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        domain = [('state', '=', 'published')]
        if not is_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        articles = env['help.article'].sudo().search(domain, order='sequence, name')
        categories = env['help.category'].sudo().search([('active', '=', True)], order='sequence, name')

        # Filter categories to only those that have accessible articles
        cat_ids = articles.mapped('category_id').ids
        categories = categories.filtered(lambda c: c.id in cat_ids)

        featured = articles.filtered('is_featured')
        recent = articles.sorted('write_date', reverse=True)[:6]

        params = env['ir.config_parameter'].sudo()
        centre_name = params.get_param('help_centre.name', 'Help Centre')
        tagline = params.get_param('help_centre.tagline', 'Find answers, guides, and step-by-step instructions')

        return request.render('help_centre.website_help_index', {
            'articles': articles,
            'categories': categories,
            'featured': featured,
            'recent': recent,
            'is_internal': is_internal,
            'centre_name': centre_name,
            'tagline': tagline,
            'search_query': '',
        })

    @http.route('/help/article/<string:slug>', type='http', auth='public', website=True)
    def article(self, slug, **kwargs):
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        article = env['help.article'].sudo().search([
            ('slug', '=', slug),
            ('state', '=', 'published'),
        ], limit=1)

        if not article:
            return request.not_found()

        # Audience enforcement
        if article.audience == 'internal' and not is_internal:
            return request.redirect(f'/web/login?redirect=/help/article/{slug}')
        if article.audience == 'external' and is_internal:
            pass  # internal users can also read external articles
        # both: always accessible

        # Increment view counter (fire-and-forget via raw SQL)
        article._increment_view()

        # Related articles: same category or overlapping tags
        related_domain = [('state', '=', 'published'), ('id', '!=', article.id)]
        if not is_internal:
            related_domain += [('audience', 'in', ('external', 'both'))]
        if article.category_id:
            related = env['help.article'].sudo().search(
                related_domain + [('category_id', '=', article.category_id.id)], limit=3
            )
        else:
            related = env['help.article'].sudo().browse([])
        if len(related) < 3 and article.tag_ids:
            extra = env['help.article'].sudo().search(
                related_domain + [('tag_ids', 'in', article.tag_ids.ids),
                                  ('id', 'not in', related.ids)],
                limit=3 - len(related),
            )
            related = related | extra

        params = env['ir.config_parameter'].sudo()
        centre_name = params.get_param('help_centre.name', 'Help Centre')

        return request.render('help_centre.website_help_article', {
            'article': article,
            'related': related,
            'is_internal': is_internal,
            'centre_name': centre_name,
        })

    @http.route('/help/contents', type='http', auth='public', website=True)
    def contents(self, **kwargs):
        """
        Full navigation tree of all published Help Centre articles organised
        by category hierarchy.  Registered as a website page so it appears in
        Website → Pages.
        """
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        domain = [('state', '=', 'published')]
        if not is_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        articles = env['help.article'].sudo().search(
            domain, order='sequence, name'
        )

        # Build articles_by_cat: {category_id: [article, ...]}
        articles_by_cat = {}
        uncategorised = []
        for a in articles:
            if a.category_id:
                articles_by_cat.setdefault(a.category_id.id, []).append(a)
            else:
                uncategorised.append(a)

        # Load all categories that have at least one accessible article
        cat_ids_with_articles = set(articles_by_cat.keys())
        all_cats = env['help.category'].sudo().search(
            [('active', '=', True)], order='sequence, name'
        )
        # Include a category if it or any of its descendants have articles
        def _has_articles(cat):
            if cat.id in cat_ids_with_articles:
                return True
            return any(_has_articles(c) for c in cat.child_ids)

        # Root categories only (no parent_id)
        root_categories = all_cats.filtered(
            lambda c: not c.parent_id and _has_articles(c)
        )

        params = env['ir.config_parameter'].sudo()
        centre_name = params.get_param('help_centre.name', 'Help Centre')

        return request.render('help_centre.website_help_contents', {
            'root_categories': root_categories,
            'articles_by_cat': articles_by_cat,
            'uncategorised': uncategorised,
            'total_articles': len(articles),
            'total_categories': len(root_categories),
            'is_internal': is_internal,
            'centre_name': centre_name,
        })

    @http.route('/help/search', type='http', auth='public', website=True)
    def search(self, q='', **kwargs):
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        domain = [('state', '=', 'published')]
        if not is_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        articles = env['help.article'].sudo().browse([])
        if q:
            ai_svc = env['help.ai.service']
            articles, _ = ai_svc.search_articles_for_context(
                q, include_internal=is_internal, limit=20
            )

        params = env['ir.config_parameter'].sudo()
        centre_name = params.get_param('help_centre.name', 'Help Centre')

        return request.render('help_centre.website_help_index', {
            'articles': articles,
            'categories': env['help.category'].sudo().browse([]),
            'featured': env['help.article'].sudo().browse([]),
            'recent': env['help.article'].sudo().browse([]),
            'is_internal': is_internal,
            'centre_name': centre_name,
            'tagline': f'Search results for "{q}"' if q else 'Search',
            'search_query': q,
        })

    # ─────────────────────────────────────────────────────────────────────────
    # JSON API — KC Bot widget
    # ─────────────────────────────────────────────────────────────────────────

    @http.route('/help/api/suggestions', type='jsonrpc', auth='public')
    def suggestions(self, q='', **kwargs):
        """Real-time article title suggestions for the KC Bot search bar."""
        if not q or len(q) < 2:
            return []

        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        domain = [('state', '=', 'published'), ('name', 'ilike', q)]
        if not is_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        articles = env['help.article'].sudo().search(domain, limit=6)
        return [
            {
                'id': a.id,
                'name': a.name,
                'slug': a.slug,
                'category': a.category_id.name or '',
                'read_time': a.read_time_minutes,
            }
            for a in articles
        ]

    @http.route('/help/api/article/<int:article_id>', type='jsonrpc', auth='public')
    def get_article_content(self, article_id, **kwargs):
        """Return article content for in-panel rendering (KC Bot article view)."""
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        article = env['help.article'].sudo().browse(article_id).exists()
        if not article or article.state != 'published':
            return {'error': 'not_found'}

        if article.audience == 'internal' and not is_internal:
            return {'error': 'auth_required', 'login_url': f'/web/login?redirect=/help/article/{article.slug}'}

        article._increment_view()

        return {
            'id': article.id,
            'name': article.name,
            'slug': article.slug,
            'content': article.content or '',
            'summary': article.summary or '',
            'read_time': article.read_time_minutes,
            'helpful_count': article.helpful_count,
            'not_helpful_count': article.not_helpful_count,
            'category': article.category_id.name or '',
            'tags': article.tag_ids.mapped('name'),
            'url': f'/help/article/{article.slug}',
        }

    @http.route('/help/api/featured', type='jsonrpc', auth='public')
    def get_featured(self, **kwargs):
        """Return featured + recent articles for the KC Bot home tab."""
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        domain = [('state', '=', 'published')]
        if not is_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        featured = env['help.article'].sudo().search(
            domain + [('is_featured', '=', True)], limit=4, order='sequence, name'
        )
        recent = env['help.article'].sudo().search(
            domain + [('id', 'not in', featured.ids)], limit=5, order='write_date desc'
        )

        def _serialize(articles):
            return [
                {
                    'id': a.id,
                    'name': a.name,
                    'slug': a.slug,
                    'summary': a.summary or '',
                    'category': a.category_id.name or '',
                    'read_time': a.read_time_minutes,
                }
                for a in articles
            ]

        return {
            'featured': _serialize(featured),
            'recent': _serialize(recent),
        }

    @http.route('/help/api/rate', type='jsonrpc', auth='public', csrf=False)
    def rate_article(self, article_id, helpful, **kwargs):
        """Record a thumbs-up or thumbs-down for an article."""
        env = request.env
        article = env['help.article'].sudo().browse(int(article_id)).exists()
        if not article:
            return {'error': 'not_found'}
        article._rate(bool(helpful))
        return {
            'helpful_count': article.helpful_count,
            'not_helpful_count': article.not_helpful_count,
        }

    @http.route('/help/chat', type='jsonrpc', auth='public', csrf=False)
    def chat(self, message, session_token=None, context_url=None, **kwargs):
        """
        Main KC Bot chat endpoint.

        :param message:       User's text message.
        :param session_token: Session UUID from localStorage; creates a new session if absent.
        :param context_url:   Current page URL so the bot can weight contextual articles.
        """
        env = request.env
        is_internal = bool(request.session.uid and not self._is_portal_user(env))

        if not message or not message.strip():
            return {'error': 'empty_message'}

        # ── Session ────────────────────────────────────────────────────────────
        session = self._get_or_create_session(env, session_token, is_internal)

        # ── Save user message ──────────────────────────────────────────────────
        env['help.chatbot.message'].sudo().create({
            'session_id': session.id,
            'role': 'user',
            'content': message,
        })

        # ── Article retrieval ──────────────────────────────────────────────────
        ai_svc = env['help.ai.service']
        articles, article_context = ai_svc.search_articles_for_context(
            message, include_internal=is_internal, limit=4
        )

        # Build conversation history (last 10 exchanges)
        history_records = session.message_ids.sorted('id')
        history = [
            {'role': m.role, 'content': m.content}
            for m in history_records[-20:]  # last 20 messages = 10 exchanges
        ]

        # ── AI call ────────────────────────────────────────────────────────────
        try:
            reply = ai_svc.chat(history, article_context=article_context)
        except Exception as e:
            _logger.warning('Help Centre chatbot AI error: %s', e)
            reply = (
                "I'm sorry, I wasn't able to process your request right now. "
                "Please check your AI provider settings or try again in a moment."
            )

        # ── Save assistant reply ───────────────────────────────────────────────
        msg_record = env['help.chatbot.message'].sudo().create({
            'session_id': session.id,
            'role': 'assistant',
            'content': reply,
        })
        if articles:
            msg_record.article_ids = articles

        return {
            'response': reply,
            'session_token': session.session_token,
            'articles': [
                {
                    'id': a.id,
                    'name': a.name,
                    'slug': a.slug,
                    'url': f'/help/article/{a.slug}',
                    'summary': a.summary or '',
                    'read_time': a.read_time_minutes,
                }
                for a in articles
            ],
        }

    @http.route('/help/api/widget_config', type='jsonrpc', auth='public')
    def widget_config(self, **kwargs):
        """Return widget configuration for JS — helpdesk integration state, auth, and branding."""
        params = request.env['ir.config_parameter'].sudo()
        helpdesk_enabled = params.get_param('help_centre.helpdesk_enabled', 'False') == 'True'
        return {
            'helpdesk_enabled': helpdesk_enabled,
            'user_authenticated': bool(request.session.uid),
            # Branding
            'ai_name': params.get_param('help_centre.ai_name', 'KC Bot'),
            'ai_welcome_message': params.get_param('help_centre.ai_welcome_message', ''),
            'primary_color': params.get_param('help_centre.primary_color', '#5b4fc8'),
        }

    @http.route('/help/api/create_ticket', type='jsonrpc', auth='public', csrf=False)
    def create_ticket(self, subject, description='', **kwargs):
        """Create a helpdesk ticket from the Help widget.  Requires an authenticated session."""
        if not request.session.uid:
            return {'error': 'auth_required', 'message': 'You must be logged in to lodge a ticket.'}

        params = request.env['ir.config_parameter'].sudo()
        if params.get_param('help_centre.helpdesk_enabled', 'False') != 'True':
            return {'error': 'helpdesk_disabled', 'message': 'Helpdesk integration is not enabled.'}

        if not subject or not subject.strip():
            return {'error': 'subject_required', 'message': 'Please enter a subject for your ticket.'}

        if 'helpdesk.ticket' not in request.env:
            return {'error': 'helpdesk_not_installed', 'message': 'Helpdesk module is not installed.'}

        team_id = int(params.get_param('help_centre.helpdesk_team_id', '0') or '0')
        user = request.env['res.users'].sudo().browse(request.session.uid)

        vals = {
            'name': subject.strip(),
            'description': description or '',
            'user_id': request.session.uid,
            'partner_id': user.partner_id.id,
        }
        if team_id:
            vals['team_id'] = team_id

        ticket = request.env['helpdesk.ticket'].sudo().create(vals)
        _logger.info('Help Centre: created helpdesk ticket #%s for user %s', ticket.id, user.name)

        return {
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _is_portal_user(self, env):
        if not request.session.uid:
            return False
        user = env['res.users'].sudo().browse(request.session.uid)
        return user.has_group('base.group_portal')

    def _get_or_create_session(self, env, session_token, is_internal):
        """Find existing session by token, or create a new one."""
        Session = env['help.chatbot.session'].sudo()

        if session_token:
            session = Session.search([('session_token', '=', session_token)], limit=1)
            if session:
                return session

        vals = {
            'session_token': session_token or str(uuid.uuid4()),
            'visitor_ip': request.httprequest.environ.get('REMOTE_ADDR', ''),
        }
        if is_internal and request.session.uid:
            vals['user_id'] = request.session.uid

        return Session.create(vals)
