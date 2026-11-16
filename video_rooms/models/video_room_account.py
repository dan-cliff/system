# -*- coding: utf-8 -*-
from odoo import fields, models


class VideoRoomAccount(models.Model):
    """A platform account a room can be signed in with (Configuration), only for
    hosts that refuse browser guests (DESIGN.md section 6b). Recommended: sign
    in once on the Room Display and keep only the login name here - the
    browser keeps the session, and no password is stored in Odoo."""
    _name = 'video.room.account'
    _description = 'Video Room Platform Account'
    _order = 'platform_id, name'

    name = fields.Char(required=True, help='e.g. "Board Room Google account".')
    active = fields.Boolean(default=True)
    room_id = fields.Many2one('video.room', help='Empty: any room may use it.')
    platform_id = fields.Many2one('video.room.platform', required=True)
    login = fields.Char(groups='base.group_system')
    # TODO(build), only if DESIGN.md Q16 says passwords must be kept: an encrypted secret,
    #              groups='base.group_system', sent to the Display only for a sign-in command.
    signed_in_on = fields.Datetime(readonly=True, help='When the Display last reported this account signed in.')
