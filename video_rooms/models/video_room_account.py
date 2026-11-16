# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomAccount(models.Model):
    """A platform account a room can be signed in with, for hosts that refuse
    browser guests (Configuration). Decided: sign in once on the Room Display and
    keep NO password in Odoo - the browser keeps the session; Odoo only notes the
    account and when the Display last reported it signed in (DESIGN.md §6b)."""
    _name = 'video.room.account'
    _description = 'Video Room Platform Account'
    _order = 'platform_id, name'

    name = fields.Char(required=True, help='e.g. "Board Room Google account".')
    active = fields.Boolean(default=True)
    room_id = fields.Many2one('video.room', ondelete='cascade', help='Empty: any room may use it.')
    platform_id = fields.Many2one('video.room.platform', required=True)
    login = fields.Char(help='The account\'s sign-in name (no password is kept).')
    signed_in_on = fields.Datetime(readonly=True, help='When the Display last reported this account signed in.')
