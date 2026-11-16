# -*- coding: utf-8 -*-
from odoo import models


class VideoRoomCall(models.Model):
    """A call's Organiser (who invited the room) as an Account and Contact."""
    _name = 'video.room.call'
    _inherit = ['video.room.call', 'advanced.accounts.mixin']
    _adv_partner_field = 'organiser_partner_id'
