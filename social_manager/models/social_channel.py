import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .social_access import LEVEL_KEYS, LEVEL_LABELS

_logger = logging.getLogger(__name__)


class SocialChannel(models.Model):
    """A Page / Channel / profile posts are published to (a Facebook Page, a
    YouTube channel, a LinkedIn organisation, an X account, ...)."""
    _name = 'social.channel'
    _inherit = ['social.access.mixin', 'mail.thread']
    _description = 'Social Page / Channel'
    _order = 'platform_id, name'

    name = fields.Char(required=True, tracking=True)
    platform_id = fields.Many2one('social.platform', string='Platform', required=True,
                                  ondelete='cascade', index=True, tracking=True)
    platform_code = fields.Selection(related='platform_id.code')
    account_id = fields.Many2one('social.account', string='Connected Account', ondelete='set null',
                                 tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    active = fields.Boolean(default=True)
    color = fields.Integer()
    external_id = fields.Char(string='Page / Channel ID', readonly=True, index=True)
    external_username = fields.Char(string='Handle', readonly=True)
    external_url = fields.Char(string='URL', readonly=True)
    image_url = fields.Char(readonly=True)
    access_token = fields.Char(groups='base.group_system', copy=False,
                               help='Page-specific token, for platforms that issue one (e.g. Facebook Pages).')
    follower_count = fields.Integer(string='Audience', readonly=True,
                                    help='Followers / subscribers on the platform.')
    # Technical connection state, set by the code.
    connection_state = fields.Selection([
        ('connected', 'Connected'),
        ('expired', 'Needs Reconnecting'),
        ('error', 'Error'),
    ], default='connected', readonly=True, tracking=True)
    last_error = fields.Text(readonly=True)
    last_sync = fields.Datetime(string='Last Synchronised', readonly=True)

    is_monetised = fields.Boolean(string='Monetised', tracking=True,
                                  help='Income is earned from this Page / Channel\'s content.')
    platform_monetised = fields.Boolean(related='platform_id.is_monetised', string='Platform Monetised')

    publication_ids = fields.One2many('social.post.publication', 'channel_id', string='Published Posts')
    income_ids = fields.One2many('social.income', 'channel_id', string='Income')
    income_total = fields.Monetary(string='Total Income', compute='_compute_income')
    income_uninvoiced = fields.Monetary(string='Not Yet Invoiced', compute='_compute_income')
    post_count = fields.Integer(compute='_compute_post_count')
    comment_count = fields.Integer(compute='_compute_post_count')
    flagged_comment_count = fields.Integer(compute='_compute_post_count')

    access_group_ids = fields.Many2many(
        'res.groups', 'social_channel_access_group_rel', 'channel_id', 'group_id',
        string='Access Groups', compute='_compute_access_group_ids', store=True,
        help='Every permission group of this Page / Channel and of its Platform; users holding '
             'any of them can see the Page / Channel and its posts.')

    @api.depends(*['group_%s_id' % key for key in LEVEL_KEYS],
                 *['platform_id.group_%s_id' % key for key in LEVEL_KEYS])
    def _compute_access_group_ids(self):
        for channel in self:
            channel.access_group_ids = channel._social_access_groups() | channel.platform_id._social_access_groups()

    @api.depends('income_ids.amount', 'income_ids.invoice_line_id')
    def _compute_income(self):
        for channel in self:
            channel.income_total = sum(channel.income_ids.mapped('amount'))
            channel.income_uninvoiced = sum(
                channel.income_ids.filtered(lambda i: not i.invoice_line_id).mapped('amount'))

    def _compute_post_count(self):
        Comment = self.env['social.comment']
        for channel in self:
            channel.post_count = self.env['social.post'].search_count([('channel_ids', 'in', channel.id)])
            channel.comment_count = Comment.search_count([('channel_id', '=', channel.id)])
            channel.flagged_comment_count = Comment.search_count([
                ('channel_id', '=', channel.id), ('needs_moderation', '=', True)])

    @api.onchange('platform_id')
    def _onchange_platform_id(self):
        if self.platform_id and not self._origin.id:
            self.is_monetised = self.platform_id.is_monetised

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def _social_access_label(self):
        self.ensure_one()
        return '%s - %s' % (self.platform_id.name, self.name)

    def _social_access_sequence(self):
        return 1000 + (self.platform_id.sequence or 10)

    def _social_access_rename_fields(self):
        return {'name', 'platform_id'}

    @api.model
    def _is_social_admin(self, user=None):
        user = user or self.env.user
        return self.env.su or user.has_group('social_manager.group_social_manager')

    def _user_has_level(self, level, user=None):
        """True when the user holds `level` on every channel in self (directly or via its Platform)."""
        user = user or self.env.user
        if self._is_social_admin(user):
            return True
        user_groups = user.sudo().all_group_ids
        for channel in self.sudo():
            groups = channel['group_%s_id' % level] | channel.platform_id['group_%s_id' % level]
            if not groups & user_groups:
                return False
        return True

    def _check_level(self, level, what=None):
        """Raise AccessError unless the current user holds `level` on every channel in self."""
        for channel in self:
            if not channel._user_has_level(level):
                raise AccessError(
                    'You need the "%s" permission on %s to %s.'
                    % (LEVEL_LABELS[level], channel._social_access_label(), what or 'do this')
                )

    def _get_provider(self):
        self.ensure_one()
        return self.platform_id._get_provider(self.sudo().account_id)

    def _get_access_token(self):
        """The token to call the platform's API for this channel."""
        self.ensure_one()
        channel = self.sudo()
        if channel.access_token:
            return channel.access_token
        if not channel.account_id:
            raise UserError('%s is not connected to an account - connect it from Platforms.' % channel.name)
        return channel.account_id._get_access_token()

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------
    def action_sync(self):
        """Fetch the latest metrics and comments of this channel's published posts."""
        for channel in self:
            publications = channel.publication_ids.filtered(lambda p: p.state == 'posted' and p.external_id)
            publications._sync_from_platform()
            channel.sudo().last_sync = fields.Datetime.now()
        return True

    def action_fetch_income(self):
        """Import income reported by the platform's API (where the platform provides it)."""
        for channel in self:
            channel._fetch_income()
        return True

    def _fetch_income(self, date_from=None, date_to=None):
        self.ensure_one()
        if not self.is_monetised:
            return
        date_to = date_to or fields.Date.context_today(self)
        date_from = date_from or fields.Date.subtract(date_to, days=30)
        provider = self._get_provider()
        try:
            rows = provider.fetch_income(self, date_from, date_to)
        except UserError as exc:
            _logger.info('Could not fetch income for %s: %s', self.display_name, exc)
            return
        self.env['social.income'].sudo()._import_rows(self, rows)

    @api.model
    def _cron_sync(self):
        channels = self.search([('connection_state', '=', 'connected'), ('account_id', '!=', False)])
        for channel in channels:
            try:
                with self.env.cr.savepoint():
                    channel.action_sync()
                    if channel.is_monetised:
                        channel._fetch_income()
            except Exception as exc:  # keep syncing the other channels
                _logger.warning('Social Manager: synchronising %s failed: %s', channel.display_name, exc)
                channel.sudo().write({'last_error': str(exc)})

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_view_posts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_post')
        action['domain'] = [('channel_ids', 'in', self.id)]
        action['context'] = {'default_channel_ids': [self.id]}
        return action

    def action_view_comments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_comment')
        action['domain'] = [('channel_id', '=', self.id)]
        return action

    def action_view_income(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_income')
        action['domain'] = [('channel_id', '=', self.id)]
        action['context'] = {'default_channel_id': self.id}
        return action
