# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ── Work Centre app: how workers sign in (same choices as On Site kiosks) ──
    mrp_terminal_identify_badge = fields.Boolean(
        string='Badge Scan (Camera)', default=True,
        help="The device's camera is always on, ready to read the QR code or barcode on a worker's "
             "ID badge (the employee's Badge ID in Personnel).",
    )
    mrp_terminal_identify_reader = fields.Boolean(
        string='External RFID / Barcode Reader',
        help='Workers scan their ID badge on an RFID or barcode reader connected to the device '
             '(one that types the Badge ID, like a keyboard). Replaces the camera.',
    )
    mrp_terminal_identify_name = fields.Boolean(
        string='Select Name', default=True,
        help='Workers find and tap their name in the Work Centre app.',
    )
    mrp_terminal_require_pin = fields.Boolean(
        string='Require PIN', default=True,
        help='Workers who select their name must also enter their employee PIN.',
    )
    mrp_terminal_idle_minutes = fields.Integer(
        string='Sign Out After (Minutes)', default=10,
        help='The Work Centre app signs the worker out after this many minutes without a tap, '
             'ready for the next one. 0 keeps them signed in until they sign out.',
    )

    # ── Work Centre app: offline use ──
    mrp_terminal_offline = fields.Boolean(
        string='Allow Offline Use', default=True,
        help='The Work Centre app keeps a copy of its workers and work orders, so work can be '
             'recorded without a connection. It syncs when the connection returns.',
    )
    mrp_terminal_offline_hours = fields.Integer(
        string='Work Offline For (Hours)', default=24,
        help='How long the Work Centre app keeps recording work without reaching Odoo. After '
             'that it asks for a connection, so its copy of the work orders never gets too old.',
    )
    mrp_terminal_refresh_minutes = fields.Integer(
        string='Refresh Every (Minutes)', default=5,
        help='How often the Work Centre app refreshes its copy of workers and work orders while online.',
    )

    # ── Work Centre app: finishing ──
    mrp_terminal_close_production = fields.Boolean(
        string='Produce When the Last Work Order Ends', default=True,
        help='When a worker finishes the last work order of a manufacturing order in the Work Centre '
             'app, the order is marked as done (Produce) straight away. Orders that need a decision '
             '(e.g. serial numbers for several units) are left for the office to finish.',
    )
