# -*- coding: utf-8 -*-
import re
import urllib.parse

from odoo import api, fields, models


class VideoRoomPlatform(models.Model):
    """A video conferencing platform a room can join (option model under
    Configuration). Recognised from a meeting link by its URL patterns."""
    _name = 'video.room.platform'
    _description = 'Video Conferencing Platform'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Technical: the driver the Room Display uses (extension/drivers/<driver>.js).
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
    join_url_template = fields.Char(
        string='Join Link From ID',
        help='Builds a link from a meeting ID and passcode when an invite gives no link: {code} and '
             '{passcode} are replaced, e.g. https://app.zoom.us/wc/join/{code}?pwd={passcode}')
    note = fields.Html(help='What hosts need to allow for us to join, known limits, ...')

    @api.model
    def _detect(self, url):
        """The active platform a meeting link belongs to (empty recordset if unknown)."""
        if not url:
            return self.browse()
        for platform in self.search([]):
            for pattern in (platform.url_patterns or '').splitlines():
                pattern = pattern.strip()
                if not pattern:
                    continue
                try:
                    if re.search(pattern, url, re.IGNORECASE):
                        return platform
                except re.error:
                    continue
        return self.browse()

    def _build_join_url(self, code, passcode=''):
        """A join link from a meeting ID / code and passcode, or ''."""
        self.ensure_one()
        if not self.join_url_template or not code:
            return ''
        clean = re.sub(r'\s+', '', code) if self.driver in ('zoom', 'teams', 'webex') else code.strip()
        url = self.join_url_template.replace('{code}', urllib.parse.quote(clean, safe='-'))
        url = url.replace('{passcode}', urllib.parse.quote((passcode or '').strip(), safe=''))
        return url.rstrip('?=&') if not passcode else url
