import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .nextcloud_api import NextcloudError

_logger = logging.getLogger(__name__)

# failed folders are retried by the cron this many times
MAX_ATTEMPTS = 5


class NextcloudFolder(models.Model):
    """The Nextcloud folder of one Odoo record."""
    _name = 'nextcloud.folder'
    _description = 'Nextcloud Folder'
    _order = 'id desc'
    _rec_name = 'path'

    rule_id = fields.Many2one(
        'nextcloud.folder.rule', string='Folder Rule', required=True, index=True,
        ondelete='cascade')
    res_model = fields.Char(string='Model', required=True, index=True, readonly=True)
    res_id = fields.Many2oneReference(
        string='Record ID', model_field='res_model', required=True, index=True, readonly=True)
    res_name = fields.Char(string='Record', compute='_compute_res_name')
    # Technical: the queue state the cron and the Folder button depend on.
    state = fields.Selection([
        ('pending', 'Queued'),
        ('done', 'Created'),
        ('error', 'Failed'),
    ], string='Status', required=True, default='pending', index=True, readonly=True)
    path = fields.Char(string='Path', readonly=True, help="The folder's path when it was created.")
    file_id = fields.Char(string='Nextcloud File ID', readonly=True)
    url = fields.Char(
        string='Link', readonly=True,
        help="Permanent link to the folder for people signed in to Nextcloud. It keeps "
             "working when the folder is renamed or moved in Nextcloud.")
    public_url = fields.Char(string='Public Link', readonly=True)
    error = fields.Text(string='Error', readonly=True)
    attempt_count = fields.Integer(string='Attempts', readonly=True)

    _record_uniq = models.Constraint(
        'UNIQUE (res_model, res_id)', 'This record already has a Nextcloud folder.')

    def _compute_res_name(self):
        for folder in self:
            record = folder._get_record()
            folder.res_name = record.display_name if record else _("(deleted)")

    def _get_record(self):
        self.ensure_one()
        if self.res_model not in self.env:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists()

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    @api.model
    def _queue(self, rule, records):
        """Queue folders for ``records`` (that don't have one) and wake the cron."""
        if not records:
            return self.browse()
        folders = self.sudo().create([{
            'rule_id': rule.id,
            'res_model': records._name,
            'res_id': record.id,
        } for record in records])
        self.env.ref('nextcloud_folders.ir_cron_nextcloud_folders').sudo()._trigger()
        return folders

    @api.model
    def _get_or_create_for(self, record):
        folder = self.sudo().search(
            [('res_model', '=', record._name), ('res_id', '=', record.id)], limit=1)
        if not folder:
            rule = self.env['nextcloud.folder.rule']._rule_for(record._name)
            if not rule:
                raise UserError(_("%s records don't have Nextcloud folders.", record._description))
            folder = self.sudo().create({
                'rule_id': rule.id, 'res_model': record._name, 'res_id': record.id})
        return folder

    @api.model
    def _cron_create_folders(self):
        folders = self.search([
            '|', ('state', '=', 'pending'),
            '&', ('state', '=', 'error'), ('attempt_count', '<', MAX_ATTEMPTS),
        ], order='id')
        if not folders or not self.env['nextcloud.api']._is_configured():
            return
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(folders))
        for folder in folders:
            folder._create_in_nextcloud()
            if not Cron._commit_progress(1):
                break

    # ------------------------------------------------------------------
    # Nextcloud
    # ------------------------------------------------------------------

    def _create_in_nextcloud(self, raise_error=False):
        """Create the folder in Nextcloud (and its public link), keep its
        link, and note it on the record. Errors are kept on the folder, or
        raised with ``raise_error``."""
        Api = self.env['nextcloud.api']
        for folder in self:
            record = folder._get_record()
            if not record:
                folder.write({'state': 'error', 'error': _("The record was deleted."),
                              'attempt_count': MAX_ATTEMPTS})
                continue
            try:
                segments = Api._root_folder() + folder.rule_id._folder_segments(record)
                file_id = Api._ensure_folder(segments)
                public_url = folder.public_url
                if folder.rule_id.public_link and not public_url:
                    public_url = Api._get_public_link(segments)
            except NextcloudError as e:
                _logger.warning("Nextcloud folder for %s,%s failed: %s",
                                folder.res_model, folder.res_id, e.message)
                folder.write({'state': 'error', 'error': e.message,
                              'attempt_count': folder.attempt_count + 1})
                if raise_error:
                    raise Api._user_error(e) from e
                continue
            first_time = not folder.url
            folder.write({
                'state': 'done',
                'path': '/'.join(segments),
                'file_id': file_id,
                'url': Api._folder_link(file_id),
                'public_url': public_url or False,
                'error': False,
                'attempt_count': folder.attempt_count + 1,
            })
            if first_time:
                folder._post_link(record)

    def _post_link(self, record):
        if not hasattr(record, 'message_post'):
            return
        body = Markup('%s <a href="%s" target="_blank" rel="noopener">%s</a>') % (
            _("Nextcloud folder created:"), self.url, self.path)
        record.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_retry(self):
        self.write({'state': 'pending', 'attempt_count': 0, 'error': False})
        self._create_in_nextcloud(raise_error=len(self) == 1)

    def action_open_folder(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.url, 'target': 'new'}

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
        }
