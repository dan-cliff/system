import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .postmark_api import EVENTS_WEBHOOK_PATH, PostmarkError

_logger = logging.getLogger(__name__)

OUTBOUND_STREAM_TYPES = ('Transactional', 'Broadcasts')


class PostmarkMessageStream(models.Model):
    _name = 'postmark.message.stream'
    _description = 'Postmark Message Stream'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    stream_id = fields.Char(
        string='Stream ID', required=True, copy=False,
        help="Postmark's identifier for the stream (e.g. \"outbound\"). "
             "Lowercase letters, numbers and dashes; it can't be changed "
             "once the stream exists in Postmark.")
    # Postmark's own stream kinds: the send code relies on these exact values,
    # so they are a technical selection rather than a configurable list.
    stream_type = fields.Selection(
        [('Transactional', 'Transactional'),
         ('Broadcasts', 'Broadcasts'),
         ('Inbound', 'Inbound')],
        required=True, default='Transactional')
    description = fields.Char()
    alias_id = fields.Many2one(
        'mail.alias', string='Alias', ondelete='set null', readonly=True,
        help="The Odoo alias this stream was created for.")
    webhook_id = fields.Integer(
        string='Postmark Webhook ID', readonly=True, copy=False,
        help="ID of the bounce / spam complaint webhook registered on this stream.")

    _stream_id_unique = models.Constraint(
        'UNIQUE(stream_id)', 'A Postmark message stream with this Stream ID already exists.')

    @api.constrains('stream_id')
    def _check_stream_id(self):
        for stream in self:
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,29}', stream.stream_id or ''):
                raise UserError(_(
                    "The Stream ID \"%s\" must be 1-30 lowercase letters, numbers or dashes.",
                    stream.stream_id))

    @api.depends('name', 'stream_id')
    def _compute_display_name(self):
        for stream in self:
            stream.display_name = f"{stream.name} ({stream.stream_id})" if stream.stream_id else stream.name

    # ------------------------------------------------------------------
    # Keep Postmark in step with changes made in Odoo
    # ------------------------------------------------------------------

    def _push_enabled(self):
        Api = self.env['postmark.api']
        return (not self.env.context.get('postmark_no_push')
                and Api._is_configured() and not Api._calls_disabled())

    @api.model_create_multi
    def create(self, vals_list):
        streams = super().create(vals_list)
        if streams._push_enabled():
            for stream in streams:
                stream._postmark_create_remote()
        return streams

    def write(self, vals):
        res = super().write(vals)
        if self._push_enabled():
            if {'name', 'description'} & set(vals):
                for stream in self:
                    try:
                        self.env['postmark.api']._request(
                            'PATCH', f'/message-streams/{stream.stream_id}',
                            {'Name': stream.name, 'Description': stream.description or ''})
                    except PostmarkError as e:
                        raise self.env['postmark.api']._user_error(e) from e
            if 'active' in vals:
                action = 'unarchive' if vals['active'] else 'archive'
                for stream in self:
                    try:
                        self.env['postmark.api']._request(
                            'POST', f'/message-streams/{stream.stream_id}/{action}', {})
                    except PostmarkError as e:
                        raise self.env['postmark.api']._user_error(e) from e
        return res

    def _postmark_create_remote(self):
        """Create this stream in Postmark, or adopt it if it already exists."""
        self.ensure_one()
        Api = self.env['postmark.api']
        try:
            Api._request('POST', '/message-streams', {
                'ID': self.stream_id,
                'Name': self.name,
                'MessageStreamType': self.stream_type,
                'Description': self.description or '',
            })
        except PostmarkError as e:
            try:
                Api._request('GET', f'/message-streams/{self.stream_id}')
            except PostmarkError:
                raise Api._user_error(e) from e
        if self.stream_type in OUTBOUND_STREAM_TYPES:
            self._postmark_configure_webhook()

    # ------------------------------------------------------------------
    # Sync from Postmark
    # ------------------------------------------------------------------

    @api.model
    def _postmark_sync_from_server(self):
        """Create / update a stream record for every stream on the Postmark server."""
        data = self.env['postmark.api']._request(
            'GET', '/message-streams',
            params={'MessageStreamType': 'All', 'IncludeArchivedStreams': 'false'})
        Stream = self.with_context(active_test=False, postmark_no_push=True)
        for remote in data.get('MessageStreams') or []:
            vals = {
                'name': remote.get('Name') or remote['ID'],
                'stream_type': remote.get('MessageStreamType') or 'Transactional',
                'description': remote.get('Description') or False,
                'active': True,
            }
            stream = Stream.search([('stream_id', '=', remote['ID'])], limit=1)
            if stream:
                stream.write(vals)
            else:
                Stream.create(dict(vals, stream_id=remote['ID']))
        return data

    def _postmark_configure_webhook(self):
        """Register (or refresh) our bounce / spam / delivery webhook on this stream."""
        self.ensure_one()
        Api = self.env['postmark.api']
        settings = self.env['res.config.settings']
        user, password = settings._postmark_webhook_credentials()
        url = settings._postmark_base_url() + EVENTS_WEBHOOK_PATH
        payload = {
            'Url': url,
            'HttpAuth': {'Username': user, 'Password': password},
            'Triggers': {
                'Bounce': {'Enabled': True, 'IncludeContent': False},
                'SpamComplaint': {'Enabled': True, 'IncludeContent': False},
                'Delivery': {'Enabled': True},
            },
        }
        webhook_id = self.webhook_id
        if not webhook_id:
            existing = Api._request('GET', '/webhooks', params={'MessageStream': self.stream_id})
            for webhook in existing.get('Webhooks') or []:
                if (webhook.get('Url') or '').split('?')[0] == url:
                    webhook_id = webhook['ID']
                    break
        if webhook_id:
            try:
                Api._request('PUT', f'/webhooks/{webhook_id}', payload)
            except PostmarkError as e:
                if e.status != 404:
                    raise
                webhook_id = False
        if not webhook_id:
            created = Api._request('POST', '/webhooks', dict(payload, MessageStream=self.stream_id))
            webhook_id = created.get('ID')
        self.with_context(postmark_no_push=True).write({'webhook_id': webhook_id or 0})

    # ------------------------------------------------------------------
    # Aliases
    # ------------------------------------------------------------------

    @api.model
    def _postmark_stream_id_for_alias(self, alias):
        slug = re.sub(r'[^a-z0-9]+', '-', (alias.alias_name or '').lower()).strip('-')
        return ('odoo-' + slug)[:30].rstrip('-') or 'odoo-alias'

    @api.model
    def _postmark_ensure_alias_stream(self, alias):
        """Return the transactional stream for ``alias``, creating it if needed.

        Failures (e.g. the Postmark server's stream limit) are logged and an
        empty recordset returned, so the alias falls back to the default stream.
        """
        Stream = self.with_context(active_test=False)
        stream = Stream.search([('alias_id', '=', alias.id)], limit=1)
        name = alias.alias_full_name or alias.alias_name
        description = _("Odoo alias %(alias)s (%(model)s)",
                        alias=name, model=alias.alias_model_id.name)
        try:
            with self.env.cr.savepoint():
                if stream:
                    if stream.name != name or not stream.active:
                        stream.write({'name': name, 'description': description, 'active': True})
                    return stream
                stream_id = self._postmark_stream_id_for_alias(alias)
                stream = Stream.search([('stream_id', '=', stream_id)], limit=1)
                if stream:
                    stream.with_context(postmark_no_push=True).write({'alias_id': alias.id})
                    return stream
                return self.create({
                    'name': name,
                    'stream_id': stream_id,
                    'stream_type': 'Transactional',
                    'description': description,
                    'alias_id': alias.id,
                })
        except (PostmarkError, UserError) as e:
            _logger.warning("Postmark: could not create a message stream for alias %s: %s", name, e)
            return self.browse()
