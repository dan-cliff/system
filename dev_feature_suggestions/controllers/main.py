"""The public Feature Requests forum (/feature-requests).

Anyone can browse published suggestions; signed-in customers and colleagues
can post suggestions, vote (saying how important it is and why) and comment.
Visitors have no access rights on the models: everything goes through sudo()
with the checks made here.
"""
from datetime import timedelta

from markupsafe import Markup, escape
from werkzeug.exceptions import NotFound

from odoo import fields, http
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import html2plaintext

PAGE_SIZE = 20
SORTS = {
    'top': 'Top',
    'new': 'Newest',
    'trending': 'Trending',
    'discussed': 'Most Discussed',
}


class FeatureRequests(http.Controller):

    def _visible_domain(self):
        """Suggestions a visitor may see: published ones in public categories, plus their own."""
        domain = Domain('is_published', '=', True) & Domain('merged_into_id', '=', False) & (
            Domain('category_id', '=', False) | Domain('category_id.is_public', '=', True))
        if not request.env.user._is_public():
            domain |= Domain('partner_id', '=', request.env.user.partner_id.id) & Domain('merged_into_id', '=', False)
        company = request.website.company_id
        if company:
            domain &= Domain('company_id', '=', company.id)
        return domain

    def _settings(self):
        params = request.env['ir.config_parameter'].sudo()
        return {
            'page_title': params.get_param('dev_feature_suggestions.page_title') or 'Feature Requests',
            'page_intro': params.get_param('dev_feature_suggestions.page_intro') or '',
        }

    def _get_suggestion(self, suggestion_id):
        suggestion = request.env['dev.suggestion'].sudo().browse(suggestion_id).exists()
        if not suggestion or not suggestion.filtered_domain(self._visible_domain()):
            if suggestion and suggestion.merged_into_id:
                return suggestion.merged_into_id
            raise NotFound()
        return suggestion

    def _my_votes(self, suggestions):
        if request.env.user._is_public():
            return {}
        votes = request.env['dev.suggestion.vote'].sudo().search([
            ('suggestion_id', 'in', suggestions.ids), ('partner_id', '=', request.env.user.partner_id.id)])
        return {vote.suggestion_id.id: vote for vote in votes}

    @http.route(['/feature-requests', '/feature-requests/page/<int:page>'], type='http', auth='public',
                website=True, sitemap=True)
    def index(self, page=1, q='', category=None, status=None, sort='top', **kwargs):
        Suggestion = request.env['dev.suggestion'].sudo()
        domain = self._visible_domain()
        categories = request.env['dev.suggestion.category'].sudo().search([('is_public', '=', True)])
        statuses = request.env['dev.suggestion.status'].sudo().search([('id', '!=', request.env.ref(
            'dev_feature_suggestions.status_merged').id)])
        current_category = categories.filtered(lambda c: str(c.id) == str(category))[:1]
        current_status = statuses.filtered(lambda s: str(s.id) == str(status))[:1]
        if current_category:
            domain &= Domain('category_id', '=', current_category.id)
        if current_status:
            domain &= Domain('status_id', '=', current_status.id)
        else:
            domain &= Domain('status_id.fold', '=', False) | Domain('status_id', '=', False)
        if q:
            domain &= Domain('name', 'ilike', q) | Domain('description', 'ilike', q)
        sort = sort if sort in SORTS else 'top'
        total = Suggestion.search_count(domain)
        pager = request.website.pager(
            url='/feature-requests', total=total, page=page, step=PAGE_SIZE,
            url_args={k: v for k, v in {'q': q, 'category': category, 'status': status, 'sort': sort}.items() if v})
        offset = pager['offset']
        if sort in ('trending', 'discussed'):
            suggestions = Suggestion.search(domain)
            if sort == 'trending':
                since = fields.Datetime.now() - timedelta(days=30)
                recent = dict(request.env['dev.suggestion.vote'].sudo()._read_group(
                    [('suggestion_id', 'in', suggestions.ids), ('create_date', '>=', since)],
                    ['suggestion_id'], ['weight:sum']))
                suggestions = suggestions.sorted(lambda s: (recent.get(s, 0), s.score), reverse=True)
            else:
                suggestions = suggestions.sorted(lambda s: (s.comment_count, s.score), reverse=True)
            suggestions = suggestions[offset:offset + PAGE_SIZE]
        else:
            order = 'create_date desc, id desc' if sort == 'new' else 'score desc, vote_count desc, id desc'
            suggestions = Suggestion.search(domain, order=order, limit=PAGE_SIZE, offset=offset)
        return request.render('dev_feature_suggestions.feature_requests_index', dict(
            self._settings(),
            suggestions=suggestions, pager=pager, categories=categories, statuses=statuses,
            current_category=current_category, current_status=current_status, q=q, sort=sort, sorts=SORTS,
            my_votes=self._my_votes(suggestions), is_public=request.env.user._is_public(),
            importances=request.env['dev.suggestion.importance'].sudo().search([]), html2plaintext=html2plaintext,
        ))

    @http.route('/feature-requests/<int:suggestion_id>', type='http', auth='public', website=True, sitemap=False)
    def suggestion(self, suggestion_id, **kwargs):
        suggestion = self._get_suggestion(suggestion_id)
        if suggestion.id != suggestion_id:
            return request.redirect(suggestion.website_url)
        comment = request.env.ref('mail.mt_comment')
        messages = suggestion.message_ids.filtered(
            lambda m: m.message_type == 'comment' and m.subtype_id == comment).sorted('date')
        return request.render('dev_feature_suggestions.feature_request_page', dict(
            self._settings(),
            suggestion=suggestion, messages=messages, my_vote=self._my_votes(suggestion).get(suggestion.id),
            is_public=request.env.user._is_public(),
            importances=request.env['dev.suggestion.importance'].sudo().search([]),
            voters=suggestion.vote_ids.partner_id,
        ))

    @http.route('/feature-requests/<int:suggestion_id>/vote', type='http', auth='user', methods=['POST'],
                website=True)
    def vote(self, suggestion_id, importance_id=None, note=None, remove=None, **kwargs):
        suggestion = self._get_suggestion(suggestion_id)
        partner = request.env.user.partner_id
        if remove:
            suggestion._remove_vote(partner)
        elif not suggestion.status_id.is_closed:
            importance = request.env['dev.suggestion.importance'].sudo().browse(int(importance_id or 0)).exists()
            suggestion._add_vote(partner, importance=importance or None, note=(note or '').strip()[:2000] or None,
                                 source=request.env.ref('dev_feature_suggestions.source_website'))
        return request.redirect(request.httprequest.referrer if kwargs.get('back') == 'list'
                                and request.httprequest.referrer else suggestion.website_url)

    @http.route('/feature-requests/<int:suggestion_id>/comment', type='http', auth='user', methods=['POST'],
                website=True)
    def comment(self, suggestion_id, body='', **kwargs):
        suggestion = self._get_suggestion(suggestion_id)
        text = (body or '').strip()[:5000]
        if text:
            html = Markup('<p>%s</p>') % Markup('<br/>').join(escape(line) for line in text.splitlines())
            suggestion.with_context(mail_create_nosubscribe=False).message_post(
                body=html, author_id=request.env.user.partner_id.id, message_type='comment',
                subtype_xmlid='mail.mt_comment')
        return request.redirect('%s#comments' % suggestion.website_url)

    @http.route('/feature-requests/new', type='http', auth='user', website=True, methods=['GET', 'POST'],
                sitemap=False)
    def new(self, name='', description='', category_id=None, **kwargs):
        categories = request.env['dev.suggestion.category'].sudo().search([('is_public', '=', True)])
        error = None
        if request.httprequest.method == 'POST':
            name = (name or '').strip()[:200]
            if not name:
                error = 'Give your suggestion a title.'
            else:
                category = categories.filtered(lambda c: str(c.id) == str(category_id))[:1]
                text = (description or '').strip()[:20000]
                html = Markup('').join(Markup('<p>%s</p>') % escape(p) for p in text.split('\n\n') if p.strip())
                partner = request.env.user.partner_id
                suggestion = request.env['dev.suggestion'].sudo().create({
                    'name': name,
                    'description': html or False,
                    'category_id': category.id or False,
                    'partner_id': partner.id,
                    'source_id': request.env.ref('dev_feature_suggestions.source_website').id,
                    'company_id': (request.website.company_id or request.env.company).id,
                })
                suggestion._add_vote(partner, source=request.env.ref('dev_feature_suggestions.source_website'))
                return request.redirect(suggestion.website_url)
        return request.render('dev_feature_suggestions.feature_request_new', dict(
            self._settings(), categories=categories, error=error, name=name, description=description,
            category_id=category_id))
