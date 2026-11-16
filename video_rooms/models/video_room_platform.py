# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models


class VideoRoomPlatform(models.Model):
    """A video conferencing platform a room can join (option model, under
    Configuration). Recognised from a meeting link by its URL patterns."""
    _name = 'video.room.platform'
    _description = 'Video Conferencing Platform'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: the driver the Room Display's browser extension uses
    # (extension/drivers/<driver>.js). Code depends on it, so a Selection.
    driver = fields.Selection([
        ('teams', 'Microsoft Teams'),
        ('zoom', 'Zoom'),
        ('google_meet', 'Google Meet'),
        ('webex', 'Cisco Webex'),
        ('jitsi', 'Jitsi Meet'),
        ('odoo_discuss', 'Odoo Discuss'),
    ], required=True)
    url_patterns = fields.Text(
        help='One regular expression per line, matched against a meeting link to recognise this platform.')
    note = fields.Html(help='What hosts need to allow for us to join, known limits, ...')

    @api.model
    def _detect(self, url):
        """The platform a meeting link belongs to (empty recordset if unknown)."""
        for platform in self.with_context(active_test=False).search([]):
            for pattern in (platform.url_patterns or '').splitlines():
                if pattern.strip() and re.search(pattern.strip(), url or '', re.IGNORECASE):
                    return platform
        return self.browse()
