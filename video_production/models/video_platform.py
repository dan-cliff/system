# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoPlatform(models.Model):
    _name = 'video.platform'
    _description = 'Publishing Platform'
    _order = 'name'

    name = fields.Char(string='Platform Name', required=True)
    description = fields.Text(string='Description')
    reference_id = fields.Char(
        string='Reference ID',
        help='External identifier for this platform (e.g. YouTube, TikTok).',
    )

    channel_ids = fields.One2many(
        'video.platform.channel', 'platform_id', string='Channels',
    )
    channel_count = fields.Integer(compute='_compute_channel_count', string='Channels')

    def _compute_channel_count(self):
        for rec in self:
            rec.channel_count = len(rec.channel_ids)


class VideoPlatformChannel(models.Model):
    _name = 'video.platform.channel'
    _description = 'Platform Channel'
    _order = 'platform_id, name'

    name = fields.Char(string='Channel Name', required=True)
    description = fields.Text(string='Description')
    reference_id = fields.Char(
        string='Reference ID',
        help='External identifier for this channel (e.g. YouTube channel ID).',
    )
    platform_id = fields.Many2one(
        'video.platform',
        string='Platform',
        required=True,
        ondelete='cascade',
    )

    playlist_ids = fields.One2many(
        'video.platform.playlist', 'channel_id', string='Playlists',
    )
    playlist_count = fields.Integer(compute='_compute_playlist_count', string='Playlists')

    def _compute_playlist_count(self):
        for rec in self:
            rec.playlist_count = len(rec.playlist_ids)


class VideoPlatformPlaylist(models.Model):
    _name = 'video.platform.playlist'
    _description = 'Platform Channel Playlist'
    _order = 'platform_id, channel_id, name'

    name = fields.Char(string='Playlist Name', required=True)
    description = fields.Text(string='Description')
    reference_id = fields.Char(
        string='Reference ID',
        help='External identifier for this playlist (e.g. YouTube playlist ID).',
    )
    platform_id = fields.Many2one(
        'video.platform',
        string='Platform',
        required=True,
        ondelete='cascade',
    )
    channel_id = fields.Many2one(
        'video.platform.channel',
        string='Channel',
        ondelete='set null',
        domain="[('platform_id', '=', platform_id)]",
    )
