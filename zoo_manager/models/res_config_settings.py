import requests

from odoo import fields, models
from odoo.exceptions import UserError

from ..lib import taxonomy_lookup
from .zoo_species import WIKIMEDIA_TOKEN_CACHE


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zoo_feed_warehouse_ids = fields.Many2many(
        related='company_id.zoo_feed_warehouse_ids', readonly=False,
        string='Warehouses',
        help='Which Warehouse/s are feed items stored in?',
    )
    zoo_feed_categ_ids = fields.Many2many(
        related='company_id.zoo_feed_categ_ids', readonly=False,
        string='Product Categories',
        help='Which Product Categories contain Feed items?',
    )

    # Integrations: Wikimedia OAuth 2.0, for the species picture lookups.
    zoo_wikimedia_client_id = fields.Char(
        string='Client ID', config_parameter='zoo_manager.wikimedia_client_id',
        help='Client application key of an OAuth 2.0 client registered at '
             'https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2',
    )
    zoo_wikimedia_client_secret = fields.Char(
        string='Client Secret', config_parameter='zoo_manager.wikimedia_client_secret',
        help='Client application secret shown when the OAuth 2.0 client was registered.',
    )
    zoo_wikimedia_access_token = fields.Char(
        string='Access Token', config_parameter='zoo_manager.wikimedia_access_token',
        help='For an owner-only client: the access token shown when it was registered. '
             'Used instead of the Client ID and Secret when filled in.',
    )

    def set_values(self):
        super().set_values()
        # New credentials: don't keep using a token fetched with the old ones.
        self.env['ir.config_parameter'].sudo().set_param(WIKIMEDIA_TOKEN_CACHE, False)

    def action_zoo_test_wikimedia(self):
        self.ensure_one()
        self.execute()
        Species = self.env['zoo.species']
        try:
            token = Species._wikimedia_token(raise_errors=True)
            if not token:
                raise UserError(self.env._('Fill in an Access Token, or a Client ID and Client Secret, first.'))
            username = taxonomy_lookup.wikimedia_username(token)
        except taxonomy_lookup.AuthenticationFailed as error:
            raise UserError(self.env._('Wikimedia rejected these credentials: %s', error)) from error
        except requests.RequestException as error:
            raise UserError(self.env._('Could not reach Wikimedia: %s', error)) from error
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'sticky': False,
                       'message': self.env._('Connected to Wikimedia as %s.', username)},
        }
