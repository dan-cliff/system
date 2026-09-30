import base64
import json
import logging
import re
from datetime import datetime, timezone

from odoo import _, api, models, modules
from odoo.exceptions import UserError
from odoo.tools import email_normalize, email_split

from .mandrill_api import MandrillAPI, MandrillError

_logger = logging.getLogger(__name__)

PARAM_PREFIX = 'mandrill_mail.'
INBOUND_PATH = '/mandrill_mail/inbound'
EVENTS_PATH = '/mandrill_mail/events'
# Message events the service asks Mandrill to report back (see webhooks/add).
WEBHOOK_EVENTS = ['send', 'deferral', 'hard_bounce', 'soft_bounce', 'open', 'click', 'spam', 'reject']
# Reply tracking: "sales@example.com" becomes "sales+odoo-<token>@example.com".
REPLY_TOKEN_TAG = 'odoo-'
REPLY_TOKEN_RE = re.compile(r'\+' + REPLY_TOKEN_TAG + r'([0-9a-f]{12})@', re.IGNORECASE)
POSTCOMMIT_SYNC_KEY = 'mandrill_mail.sync_routes'


class MandrillService(models.AbstractModel):
    """Shared helpers for the Mailchimp Transactional (Mandrill) service:
    configuration, inbound route / webhook syncing and event handling."""
    _name = 'mandrill.service'
    _description = 'Mailchimp Transactional Email Service'

    # ------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------

    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_PREFIX + key, default)

    @api.model
    def _set_param(self, key, value):
        self.env['ir.config_parameter'].sudo().set_param(PARAM_PREFIX + key, value)

    @api.model
    def _is_enabled(self):
        return bool(self._get_param('enabled')) and bool((self._get_param('api_key') or '').strip())

    @api.model
    def _reply_tracking_enabled(self):
        return self._is_enabled() and bool(self._get_param('reply_tracking'))

    @api.model
    def _get_api(self):
        api_key = (self._get_param('api_key') or '').strip()
        if not api_key:
            raise UserError(_("Enter your Mailchimp Transactional API key in Settings > General Settings > Emails first."))
        return MandrillAPI(api_key)

    @api.model
    def _get_url(self, path):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return base_url.rstrip('/') + path

    # ------------------------------------------------------------
    # Reply-to / reply tracking
    # ------------------------------------------------------------

    @api.model
    def _inbound_domains(self):
        """Domains Mandrill receives mail for: one per Odoo alias domain."""
        return self.env['mail.alias.domain'].sudo().search([]).mapped('name')

    @api.model
    def _get_reply_to(self, model, company=None):
        """Reply-to address configured for ``model``, falling back on the
        overall default. ``False`` means keep Odoo's own reply-to."""
        rule = self.env['mandrill.reply.route'].sudo()._find_for_model(model, company=company)
        if rule and rule.reply_to:
            return rule.reply_to
        return (self._get_param('default_reply_to') or '').strip() or False

    @api.model
    def _add_reply_token(self, reply_to, token):
        """Put ``token`` in the local part of every reply-to address that
        belongs to an inbound domain, keeping any display name."""
        domains = {d.lower() for d in self._inbound_domains()}
        if not reply_to or not domains:
            return reply_to

        def _tokenize(match):
            local, domain = match.group(1), match.group(2)
            if domain.lower() not in domains or REPLY_TOKEN_RE.search(match.group(0)):
                return match.group(0)
            return f'{local}+{REPLY_TOKEN_TAG}{token}@{domain}'

        return re.sub(r'([A-Za-z0-9._%\-+]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})', _tokenize, reply_to)

    @api.model
    def _find_reply_tokens(self, *values):
        tokens = []
        for value in values:
            for token in REPLY_TOKEN_RE.findall(value or ''):
                if token.lower() not in tokens:
                    tokens.append(token.lower())
        return tokens

    # ------------------------------------------------------------
    # Inbound routes (created / updated from mail aliases)
    # ------------------------------------------------------------

    @api.model
    def _desired_route_patterns(self):
        """``{domain: set(patterns)}`` that should route to Odoo: every mail
        alias, each domain's catchall and bounce aliases and every reply-to
        address configured in this module. With reply tracking on, each
        mailbox also gets a ``<mailbox>+*`` pattern so tokenized reply-to
        addresses reach Odoo."""
        desired = {}
        alias_domains = self.env['mail.alias.domain'].sudo().search([])
        for alias_domain in alias_domains:
            names = set(self.env['mail.alias'].sudo().search([
                ('alias_domain_id', '=', alias_domain.id), ('alias_name', '!=', False),
            ]).mapped('alias_name'))
            names |= {alias_domain.catchall_alias, alias_domain.bounce_alias}
            desired[alias_domain.name.lower()] = {n.lower() for n in names if n}

        reply_tos = self.env['mandrill.reply.route'].sudo().search([]).mapped('reply_to')
        reply_tos.append(self._get_param('default_reply_to') or '')
        for reply_to in reply_tos:
            for address in email_split(reply_to or ''):
                local, _at, domain = (email_normalize(address) or '').partition('@')
                if domain in desired and local:
                    desired[domain].add(local)

        if self._get_param('reply_tracking'):
            for domain, patterns in desired.items():
                desired[domain] = patterns | {f'{p}+*' for p in patterns}
        return desired

    @api.model
    def _sync_inbound_routes(self, raise_on_error=False):
        """Make Mandrill's inbound routes that point at this database match
        the aliases in Odoo: add missing patterns, remove stale ones. Routes
        pointing anywhere else are left alone."""
        if not self._is_enabled():
            return False
        url = self._get_url(INBOUND_PATH)
        try:
            client = self._get_api()
            existing_domains = {d['domain'].lower() for d in client.inbound_domains() or []}
            for domain, patterns in self._desired_route_patterns().items():
                if domain not in existing_domains:
                    client.add_inbound_domain(domain)
                routes = client.inbound_routes(domain) or []
                ours = {r['pattern'].lower(): r for r in routes if r.get('url') == url}
                taken = {r['pattern'].lower() for r in routes if r.get('url') != url}
                for pattern in sorted(patterns - set(ours) - taken):
                    client.add_inbound_route(domain, pattern, url)
                for pattern in sorted(set(ours) - patterns):
                    client.delete_inbound_route(ours[pattern]['id'])
        except (MandrillError, UserError) as e:
            _logger.warning("Mailchimp Transactional: inbound route sync failed: %s", e)
            if raise_on_error:
                raise UserError(_("Could not sync inbound routes with Mailchimp Transactional:\n%s", e)) from e
            return False
        return True

    @api.model
    def _schedule_route_sync(self):
        """Sync inbound routes once, after the current transaction commits,
        so a rolled-back alias change never reaches Mandrill."""
        if not self._is_enabled() or modules.module.current_test:
            return
        cr = self.env.cr
        if cr.postcommit.data.get(POSTCOMMIT_SYNC_KEY):
            return
        cr.postcommit.data[POSTCOMMIT_SYNC_KEY] = True
        dbname, uid, context = cr.dbname, self.env.uid, dict(self.env.context)

        @cr.postcommit.add
        def _sync_routes():
            db_registry = modules.registry.Registry(dbname)
            with db_registry.cursor() as new_cr:
                env = api.Environment(new_cr, uid, context)
                env['mandrill.service']._sync_inbound_routes()

    # ------------------------------------------------------------
    # Message event webhook
    # ------------------------------------------------------------

    @api.model
    def _sync_events_webhook(self):
        """Create or update the Mandrill webhook that reports delivery events
        (sent, bounced, opened...) back to this database and keep its signing
        key so the events controller can verify requests."""
        client = self._get_api()
        url = self._get_url(EVENTS_PATH)
        description = _("Odoo (%s)", self.env.cr.dbname)
        try:
            hooks = client.webhooks() or []
            hook = next((h for h in hooks if h.get('url') == url), None)
            if hook:
                hook = client.update_webhook(hook['id'], url, WEBHOOK_EVENTS, description)
            else:
                hook = client.add_webhook(url, WEBHOOK_EVENTS, description)
        except MandrillError as e:
            raise UserError(_("Could not set up the Mailchimp Transactional webhook:\n%s", e)) from e
        self._set_param('events_webhook_key', hook.get('auth_key') or '')
        return hook

    @api.model
    def _process_events(self, events):
        """Apply Mandrill message events to the email log."""
        Log = self.env['mandrill.mail.log'].sudo()
        state_by_event = {
            'send': 'sent', 'deferral': 'deferred', 'hard_bounce': 'bounced',
            'soft_bounce': 'soft_bounced', 'spam': 'spam', 'reject': 'rejected',
        }
        for event in events:
            msg = event.get('msg') or {}
            mandrill_id = msg.get('_id') or event.get('_id')
            if not mandrill_id:
                continue
            log = Log.search([('mandrill_id', '=', mandrill_id)], limit=1)
            if not log:
                continue
            kind = event.get('event')
            vals = {'last_event': kind}
            if event.get('ts'):
                vals['last_event_date'] = datetime.fromtimestamp(int(event['ts']), tz=timezone.utc).replace(tzinfo=None)
            if kind in state_by_event:
                vals['state'] = state_by_event[kind]
            if kind == 'open':
                vals['open_count'] = log.open_count + 1
            elif kind == 'click':
                vals['click_count'] = log.click_count + 1
            if kind in ('hard_bounce', 'soft_bounce', 'reject', 'spam'):
                vals['error_message'] = msg.get('bounce_description') or msg.get('diag') or kind
            log.write(vals)
            if kind == 'hard_bounce':
                log._handle_hard_bounce(msg.get('email'), vals['error_message'])

    # ------------------------------------------------------------
    # Inbound email
    # ------------------------------------------------------------

    @api.model
    def _receive_inbound_events(self, events):
        """Store each inbound email from the Mandrill webhook in the log and
        wake the processing cron. Returns the created log records."""
        Log = self.env['mandrill.mail.log'].sudo()
        logs = Log
        for event in events:
            if event.get('event') != 'inbound':
                continue
            msg = event.get('msg') or {}
            raw = msg.get('raw_msg')
            if not raw:
                continue
            headers = msg.get('headers') or {}
            to = ', '.join(
                address if not name else f'"{name}" <{address}>'
                for address, name in (msg.get('to') or [])
            )
            logs |= Log.create({
                'direction': 'inbound',
                'state': 'received',
                'subject': msg.get('subject') or '',
                'email_from': (f'"{msg["from_name"]}" <{msg.get("from_email")}>'
                               if msg.get('from_name') else msg.get('from_email')) or '',
                'email_to': to,
                'recipient': msg.get('email') or '',
                'message_id': _header(headers, 'Message-Id'),
                'in_reply_to': _header(headers, 'In-Reply-To'),
                'references': _header(headers, 'References'),
                'raw_message': base64.b64encode(raw.encode() if isinstance(raw, str) else raw),
                'metadata': json.dumps({
                    'spam_score': (msg.get('spam_report') or {}).get('score'),
                    'spf': (msg.get('spf') or {}).get('result'),
                    'dkim_valid': (msg.get('dkim') or {}).get('valid'),
                }),
            })
        if logs:
            self.env.ref('mandrill_mail.ir_cron_mandrill_process_inbound')._trigger()
        return logs


def _header(headers, name):
    value = headers.get(name)
    if value is None:
        value = next((v for k, v in headers.items() if k.lower() == name.lower()), '')
    if isinstance(value, list):
        value = value[0] if value else ''
    return value or ''
