# -*- coding: utf-8 -*-
from odoo import _, fields, models

from .iot_github import PARAM_ENABLED, PARAM_TOKEN


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    iot_github_enabled = fields.Boolean(
        string='Hold Node Programs in GitHub', config_parameter=PARAM_ENABLED,
        help="Each program with a GitHub repository is managed there: Odoo syncs every commit as a version, "
             "keeping the full history, and the Nodes update to the newest.",
    )
    iot_github_token = fields.Char(
        string='GitHub Access Token', config_parameter=PARAM_TOKEN,
        help='A fine-grained personal access token with read and write access to the contents of the '
             'program repositories.',
    )

    def action_iot_github_test(self):
        self.execute()
        user = self.env['iot.github']._get('/user')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('Connected to GitHub as %s.', user.get('login'))},
        }
