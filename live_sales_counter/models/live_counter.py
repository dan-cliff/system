import secrets
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.http import request
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import ValidationError

# Latest sales sent to the page for its feed (and to spot new sales).
RECENT_LIMIT = 25
# Sales read to light up buyers' towns on the map.
PLACES_LIMIT = 2000


def _new_token(*args):
    return secrets.token_urlsafe(24)


def _iso_utc(dt):
    """Naive UTC datetime -> ISO 8601 string the page's JavaScript can parse."""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None


class LiveCounter(models.Model):
    _name = 'live.counter'
    _description = 'Live Sales Counter'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, help='Shown as the heading of the live page.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')

    # ── Sharing ────────────────────────────────────────────────────────────
    # Technical choice the page's access check depends on.
    visibility = fields.Selection(
        [('private', 'Private - signed in users only'),
         ('public', 'Public - anyone with the link')],
        default='private', required=True,
        help='Private: only signed in Live Sales Counter users of this company can open the page.\n'
             'Public: anyone with the link can open it. Customer names and addresses are never '
             'shown, only their town and country.',
    )
    access_token = fields.Char(required=True, copy=False, readonly=True, index=True, default=_new_token)
    page_url = fields.Char(string='Page Link', compute='_compute_page_url')

    # ── What is counted ────────────────────────────────────────────────────
    # Technical choice the date range calculation depends on.
    period = fields.Selection(
        [('today', 'Today'),
         ('week', 'This Week'),
         ('month', 'This Month'),
         ('year', 'This Year'),
         ('since', 'Since a Date')],
        string='Count Sales', default='today', required=True,
    )
    date_from = fields.Date(string='Since', help='First day counted when counting sales since a date.')
    tz = fields.Selection(
        _tz_get, string='Timezone', required=True,
        default=lambda self: self.env.user.tz or 'Europe/London',
        help='Used to work out when today, this week, this month and this year start.',
    )
    include_sale_orders = fields.Boolean(
        string='Sales Orders', default=True,
        help='Confirmed sales orders, including Website / eCommerce orders and orders '
             'imported from other shops.',
    )
    team_ids = fields.Many2many(
        'crm.team', string='Sales Teams', check_company=True,
        help='Only count sales orders of these Sales Teams. Leave empty to count them all.',
    )
    pos_available = fields.Boolean(compute='_compute_pos_available')
    include_pos_orders = fields.Boolean(
        string='Point of Sale Orders', default=True,
        help='Paid Point of Sale orders (refunds are taken off).',
    )
    tax_included = fields.Boolean(
        string='Include Tax', default=True,
        help='Count order totals including tax. Untick to count amounts before tax.',
    )

    # ── Display ────────────────────────────────────────────────────────────
    show_map = fields.Boolean(string='Live Map', default=True)
    # Technical choice the page's map drawing depends on.
    map_style = fields.Selection(
        [('globe', 'Spinning Globe'), ('flat', 'Flat World Map')],
        default='globe', required=True,
    )
    show_feed = fields.Boolean(string='Latest Sales', default=True)
    show_channels = fields.Boolean(string='Sales by Channel', default=True)
    show_city = fields.Boolean(
        string='Show Towns', default=True,
        help="Show the buyer's town as well as their country in the latest sales.",
    )
    dark_theme = fields.Boolean(string='Dark Theme', default=True)
    sound = fields.Boolean(
        string='Sound on New Sale', default=False,
        help='Play a chime for each new sale. Browsers only play sound after someone '
             'clicks the page once.',
    )
    refresh_seconds = fields.Integer(
        string='Check Every (Seconds)', default=10,
        help='How often the page checks for new sales.',
    )

    _refresh_seconds_min = models.Constraint(
        'CHECK (refresh_seconds >= 5)', 'Check for new sales at most every 5 seconds.')

    @api.depends('access_token')
    def _compute_page_url(self):
        # The address the user is browsing from, so the link works even when
        # web.base.url is out of date; the configured one outside a request.
        base_url = request.httprequest.host_url.rstrip('/') if request else self.get_base_url()
        for counter in self:
            counter.page_url = f'{base_url}/live-sales/{counter.access_token}' if counter.access_token else False

    def _compute_pos_available(self):
        self.pos_available = 'pos.order' in self.env

    @api.constrains('period', 'date_from')
    def _check_date_from(self):
        for counter in self:
            if counter.period == 'since' and not counter.date_from:
                raise ValidationError(_('Choose the date to count sales from.'))

    # ── Actions ────────────────────────────────────────────────────────────
    def action_open_page(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self._page_path(), 'target': 'new'}

    def action_open_demo(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'{self._page_path()}?demo=1', 'target': 'new'}

    def _page_path(self):
        """Link relative to the site the user is on, for the Open buttons."""
        return f'/live-sales/{self.access_token}'

    def action_regenerate_token(self):
        for counter in self:
            counter.access_token = _new_token()

    # ── Page data ──────────────────────────────────────────────────────────
    @api.model
    def _get_by_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([('access_token', '=', token)], limit=1)

    def _can_view(self, user):
        """Whether ``user`` may open this counter's page."""
        self.ensure_one()
        if self.visibility == 'public':
            return True
        if user._is_public() or self.company_id not in user.company_ids:
            return False
        # Private pages follow the user's Live Sales Counter permissions.
        counter = self.with_user(user).with_company(self.company_id)
        return counter.has_access('read')

    def _period_start(self, now=None):
        """Start of the counted period, as a naive UTC datetime."""
        self.ensure_one()
        tz = pytz.timezone(self.tz or 'UTC')
        now = now or fields.Datetime.now()
        today = pytz.utc.localize(now).astimezone(tz).date()
        if self.period == 'week':
            start = today - timedelta(days=today.weekday())
        elif self.period == 'month':
            start = today.replace(day=1)
        elif self.period == 'year':
            start = today.replace(month=1, day=1)
        elif self.period == 'since' and self.date_from:
            start = self.date_from
        else:
            start = today
        return tz.localize(datetime.combine(start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    def _period_label(self):
        self.ensure_one()
        if self.period == 'since' and self.date_from:
            return _('Since %(date)s', date=self.date_from.strftime('%d/%m/%Y'))
        return dict(self._fields['period']._description_selection(self.env))[self.period]

    def _sale_domain(self, start):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'sale'),
            ('date_order', '>=', start),
        ]
        if self.team_ids:
            domain.append(('team_id', 'in', self.team_ids.ids))
        return domain

    def _pos_domain(self, start):
        return [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('paid', 'done')),
            ('date_order', '>=', start),
        ]

    def _sources(self):
        """(model, domain builder) for every sales channel this counter counts."""
        sources = []
        if self.include_sale_orders:
            sources.append(('sale.order', self._sale_domain))
        if self.include_pos_orders and 'pos.order' in self.env:
            sources.append(('pos.order', self._pos_domain))
        return sources

    def _to_company_currency(self, amount, currency):
        company_currency = self.company_id.currency_id
        if not currency or currency == company_currency:
            return amount
        return currency._convert(amount, company_currency, self.company_id, fields.Date.today())

    def _channel_groupby(self, model):
        if model == 'pos.order':
            return ['config_id']
        Order = self.env['sale.order']
        return ['website_id', 'team_id'] if 'website_id' in Order._fields else ['team_id']

    def _channel_name(self, model, groups):
        """Sales channel name from the group values of _channel_groupby."""
        if model == 'pos.order':
            return groups[0].name or _('Point of Sale')
        for record in groups:
            if record:
                return record.name
        return _('Sales')

    def _order_amount(self, order):
        """An order's amount in the company currency."""
        if order._name == 'pos.order':
            amount = order.amount_total if self.tax_included else order.amount_total - order.amount_tax
        else:
            amount = order.amount_total if self.tax_included else order.amount_untaxed
        return self.company_id.currency_id.round(self._to_company_currency(amount, order.currency_id))

    def _get_totals(self, start):
        total = 0.0
        count = 0
        channels = {}
        for model, domain_builder in self._sources():
            Order = self.env[model].sudo()
            if model == 'pos.order':
                aggregates = ['amount_total:sum', 'amount_tax:sum', '__count']
            else:
                aggregates = ['amount_total:sum', 'amount_untaxed:sum', '__count']
            groupby = ['currency_id'] + self._channel_groupby(model)
            for row in Order._read_group(domain_builder(start), groupby, aggregates):
                currency, *groups = row[:len(groupby)]
                amount_total, other, group_count = row[len(groupby):]
                if self.tax_included:
                    amount = amount_total
                elif model == 'pos.order':
                    amount = amount_total - other
                else:
                    amount = other
                amount = self._to_company_currency(amount or 0.0, currency)
                name = self._channel_name(model, groups)
                channel = channels.setdefault(name, {'name': name, 'total': 0.0, 'count': 0})
                channel['total'] += amount
                channel['count'] += group_count
                total += amount
                count += group_count
        currency = self.company_id.currency_id
        for channel in channels.values():
            channel['total'] = currency.round(channel['total'])
        return {
            'total': currency.round(total),
            'count': count,
            'channels': sorted(channels.values(), key=lambda c: -c['total']),
        }

    def _order_partner(self, order):
        if order._name == 'sale.order':
            return order.partner_shipping_id or order.partner_id
        return order.partner_id

    def _get_orders(self, start, limit):
        """The latest ``limit`` orders of every counted channel, newest first."""
        orders = []
        for model, domain_builder in self._sources():
            orders.extend(self.env[model].sudo().search(
                domain_builder(start), order='date_order desc, id desc', limit=limit))
        orders.sort(key=lambda o: o.date_order, reverse=True)
        return orders[:limit]

    def _store_location(self):
        partner = self.company_id.partner_id
        loc = self.env['live.counter.location']._locate_partners(partner)[partner.id]
        loc['name'] = self.company_id.name
        return loc

    def _order_channel(self, order):
        if order._name == 'pos.order':
            return order.config_id.name or _('Point of Sale')
        if 'website_id' in order._fields and order.website_id:
            return order.website_id.name
        return order.team_id.name or _('Sales')

    def _get_recent(self, start, store):
        orders = self._get_orders(start, RECENT_LIMIT)
        partners = self.env['res.partner'].concat(*[self._order_partner(o) for o in orders])
        located = self.env['live.counter.location']._locate_partners(partners)
        company_partner = self.company_id.partner_id
        recent = []
        for order in orders:
            partner = self._order_partner(order)
            in_store = not partner or partner == company_partner
            loc = store if in_store else located.get(partner.id)
            if not in_store and not loc.get('country') and not loc.get('city'):
                # A customer without an address: show the sale at the shop.
                loc, in_store = store, True
            recent.append({
                'key': f'{"pos" if order._name == "pos.order" else "so"}-{order.id}',
                'channel': self._order_channel(order),
                'amount': self._order_amount(order),
                'date': _iso_utc(order.date_order),
                'in_store': in_store,
                'city': loc['city'] if self.show_city else '',
                'country': loc['country'],
                'country_code': loc['country_code'],
                'lat': loc['lat'],
                'lng': loc['lng'],
            })
        return recent

    def _get_places(self, start, store):
        """Every buyer town in the period with its number of sales, for the map."""
        orders = self._get_orders(start, PLACES_LIMIT)
        company_partner = self.company_id.partner_id
        partners = self.env['res.partner'].concat(*[self._order_partner(o) for o in orders])
        located = self.env['live.counter.location']._locate_partners(partners)
        places = {}
        for order in orders:
            partner = self._order_partner(order)
            loc = store if not partner or partner == company_partner else located.get(partner.id)
            if not loc.get('country_code') and loc.get('lat') is None:
                loc = store
            key = (loc['lat'], loc['lng'], loc['country_code'])
            place = places.setdefault(key, {
                'lat': loc['lat'], 'lng': loc['lng'], 'country_code': loc['country_code'], 'count': 0,
            })
            place['count'] += 1
        return list(places.values())

    def _currency_info(self):
        currency = self.company_id.currency_id
        return {
            'name': currency.name,
            'symbol': currency.symbol,
            'position': currency.position,
            'decimals': currency.decimal_places,
        }

    def _page_config(self):
        """Settings the page needs once, when it loads."""
        self.ensure_one()
        return {
            'name': self.name,
            'company': self.company_id.name,
            'currency': self._currency_info(),
            'show_map': self.show_map,
            'map_style': self.map_style,
            'show_feed': self.show_feed,
            'show_channels': self.show_channels,
            'dark': self.dark_theme,
            'sound': self.sound,
            'refresh_seconds': max(self.refresh_seconds, 5),
            'tz': self.tz,
        }

    def _live_data(self, with_places=False):
        """Everything the live page shows. Runs as superuser: callers check access first."""
        self.ensure_one()
        counter = self.sudo()
        start = counter._period_start()
        store = counter._store_location()
        data = counter._get_totals(start)
        data.update({
            'period': counter._period_label(),
            'start': _iso_utc(start),
            'server_time': _iso_utc(fields.Datetime.now()),
            'store': store,
            'recent': counter._get_recent(start, store) if (counter.show_feed or counter.show_map) else [],
        })
        if with_places and counter.show_map:
            data['places'] = counter._get_places(start, store)
        return data
