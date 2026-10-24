from odoo import _, fields, models

from .nextcloud_api import NextcloudError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    nextcloud_url = fields.Char(
        string='Server Address',
        config_parameter='nextcloud_folders.url',
        help="The address you open Nextcloud at, e.g. https://cloud.mycompany.com. Odoo must "
             "be able to reach it over the internet (e.g. through a Cloudflare Tunnel).")
    nextcloud_username = fields.Char(
        string='Username',
        config_parameter='nextcloud_folders.username',
        help="The Nextcloud account Odoo creates the folders as. Use a service account and "
             "share the root folder with the people who need it (or make the root folder a "
             "Team Folder).")
    nextcloud_app_password = fields.Char(
        string='App Password',
        config_parameter='nextcloud_folders.app_password',
        help="An app password for that account (Nextcloud > Personal settings > Security > "
             "Devices & sessions > Create new app password).")
    nextcloud_root_folder = fields.Char(
        string='Root Folder',
        config_parameter='nextcloud_folders.root_folder',
        default='Odoo',
        help="Folder (in the service account's files) that every Odoo folder is created in, "
             "e.g. Odoo or Shared/Odoo. Leave empty to create them at the top level.")
    nextcloud_rule_count = fields.Integer(compute='_compute_nextcloud_rule_count')

    def _compute_nextcloud_rule_count(self):
        count = self.env['nextcloud.folder.rule'].search_count([])
        for settings in self:
            settings.nextcloud_rule_count = count

    def action_nextcloud_test(self):
        self.set_values()
        Api = self.env['nextcloud.api']
        try:
            name = Api._test_connection()
            if Api._root_folder():
                Api._ensure_folder(Api._root_folder())
        except NextcloudError as e:
            raise Api._user_error(e) from e
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Connected to Nextcloud"),
                'message': _("Signed in as %s.", name),
            },
        }

    def action_nextcloud_rules(self):
        return self.env['ir.actions.act_window']._for_xml_id('nextcloud_folders.nextcloud_folder_rule_action')

    def action_nextcloud_folders(self):
        return self.env['ir.actions.act_window']._for_xml_id('nextcloud_folders.nextcloud_folder_action')
