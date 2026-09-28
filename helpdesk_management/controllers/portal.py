from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import email_normalize, plaintext2html

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class HelpdeskCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'helpdesk_ticket_count' in counters:
            Ticket = request.env['helpdesk.ticket']
            values['helpdesk_ticket_count'] = Ticket.search_count([]) if Ticket.has_access('read') else 0
        return values

    # ------------------------------------------------------------
    # My tickets
    # ------------------------------------------------------------

    def _ticket_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'reference': {'label': _('Reference'), 'order': 'ticket_ref desc'},
            'name': {'label': _('Subject'), 'order': 'name'},
            'stage': {'label': _('Stage'), 'order': 'stage_id, id desc'},
        }

    def _ticket_searchbar_filters(self):
        return {
            'open': {'label': _('Open'), 'domain': [('fold', '=', False)]},
            'closed': {'label': _('Closed'), 'domain': [('fold', '=', True)]},
            'all': {'label': _('All'), 'domain': []},
        }

    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_tickets(self, page=1, sortby=None, filterby=None, search=None, **kw):
        Ticket = request.env['helpdesk.ticket']
        sortings = self._ticket_searchbar_sortings()
        filters = self._ticket_searchbar_filters()
        sortby = sortby if sortby in sortings else 'date'
        filterby = filterby if filterby in filters else 'open'

        domain = Domain(filters[filterby]['domain'])
        if search:
            domain &= Domain('name', 'ilike', search) | Domain('ticket_ref', 'ilike', search)

        count = Ticket.search_count(domain)
        pager = portal_pager(
            url='/my/tickets',
            url_args={'sortby': sortby, 'filterby': filterby, 'search': search},
            total=count, page=page, step=self._items_per_page,
        )
        tickets = Ticket.search(domain, order=sortings[sortby]['order'],
                                limit=self._items_per_page, offset=pager['offset'])
        request.session['my_tickets_history'] = tickets.ids[:100]

        values = self._prepare_portal_layout_values()
        values.update({
            'tickets': tickets,
            'page_name': 'ticket',
            'default_url': '/my/tickets',
            'pager': pager,
            'searchbar_sortings': sortings,
            'sortby': sortby,
            'searchbar_filters': filters,
            'filterby': filterby,
            'search': search,
        })
        return request.render('helpdesk_management.portal_my_tickets', values)

    @http.route('/my/tickets/<int:ticket_id>', type='http', auth='public', website=True)
    def portal_my_ticket(self, ticket_id, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access('helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        for attachment in ticket_sudo.message_ids.attachment_ids:
            attachment.generate_access_token()
        values = {
            'page_name': 'ticket',
            'ticket': ticket_sudo,
            'priority_labels': dict(ticket_sudo._fields['priority']._description_selection(request.env)),
            'can_close': ticket_sudo.allow_portal_ticket_closing and not ticket_sudo.fold
                         and bool(ticket_sudo._portal_closing_stage()),
        }
        values = self._get_page_view_values(ticket_sudo, access_token, values, 'my_tickets_history', False, **kw)
        return request.render('helpdesk_management.portal_my_ticket', values)

    @http.route('/my/tickets/<int:ticket_id>/close', type='http', auth='public', methods=['POST'], website=True)
    def portal_close_ticket(self, ticket_id, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access('helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        try:
            ticket_sudo.action_portal_close()
        except UserError:
            pass
        url = f'/my/tickets/{ticket_id}'
        return request.redirect(f'{url}?access_token={access_token}' if access_token else url)

    # ------------------------------------------------------------
    # Public "Submit a Ticket" form
    # ------------------------------------------------------------

    def _website_form_teams(self):
        return request.env['helpdesk.team'].sudo().search([('use_website_form', '=', True)])

    def _helpdesk_form_values(self, team, **kw):
        user = request.env.user
        partner = user.partner_id if not user._is_public() else request.env['res.partner']
        return {
            'team': team,
            'teams': self._website_form_teams(),
            'ticket_types': request.env['helpdesk.ticket.type'].sudo().search([]),
            'partner_name': kw.get('partner_name', partner.name or ''),
            'partner_email': kw.get('partner_email', partner.email or ''),
            'partner_phone': kw.get('partner_phone', partner.phone or ''),
            'name': kw.get('name', ''),
            'description': kw.get('description', ''),
            'ticket_type_id': kw.get('ticket_type_id', ''),
            'error': {},
        }

    @http.route('/helpdesk', type='http', auth='public', website=True, sitemap=True)
    def helpdesk_teams(self, **kw):
        teams = self._website_form_teams()
        if len(teams) == 1:
            return request.redirect(f'/helpdesk/{teams.id}')
        return request.render('helpdesk_management.helpdesk_team_select', {'teams': teams})

    @http.route('/helpdesk/<int:team_id>', type='http', auth='public', website=True, sitemap=False)
    def helpdesk_ticket_form(self, team_id, **kw):
        team = self._website_form_teams().filtered(lambda t: t.id == team_id)
        if not team:
            return request.redirect('/helpdesk')
        return request.render('helpdesk_management.helpdesk_ticket_form', self._helpdesk_form_values(team))

    @http.route('/helpdesk/<int:team_id>/submit', type='http', auth='public', methods=['POST'], website=True,
                sitemap=False)
    def helpdesk_ticket_submit(self, team_id, **kw):
        team = self._website_form_teams().filtered(lambda t: t.id == team_id)
        if not team:
            return request.redirect('/helpdesk')
        # a hidden field people can't see: bots that fill every field are dropped
        if kw.get('website_url'):
            return request.redirect('/helpdesk')

        values = self._helpdesk_form_values(team, **kw)
        email = email_normalize(kw.get('partner_email') or '')
        error = {}
        if not (kw.get('partner_name') or '').strip():
            error['partner_name'] = _('Please enter your name.')
        if not email:
            error['partner_email'] = _('Please enter a valid email address.')
        if not (kw.get('name') or '').strip():
            error['name'] = _('Please enter a subject.')
        if error:
            values['error'] = error
            return request.render('helpdesk_management.helpdesk_ticket_form', values)

        user = request.env.user
        partner = user.partner_id if not user._is_public() and user.partner_id.email_normalized == email else False
        ticket_type = request.env['helpdesk.ticket.type'].sudo().browse(
            int(kw['ticket_type_id']) if (kw.get('ticket_type_id') or '').isdigit() else 0).exists()
        ticket = request.env['helpdesk.ticket'].sudo().create({
            'name': kw['name'].strip(),
            'description': plaintext2html(kw.get('description') or ''),
            'team_id': team.id,
            'ticket_type_id': ticket_type.id,
            'partner_id': partner.id if partner else False,
            'partner_name': kw['partner_name'].strip(),
            'partner_email': email,
            'partner_phone': (kw.get('partner_phone') or '').strip(),
        })
        return request.render('helpdesk_management.helpdesk_ticket_submitted', {
            'ticket': ticket,
            'team': team,
            'is_logged_in': not user._is_public(),
        })
