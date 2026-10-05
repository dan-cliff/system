from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    in_kiosk_id = fields.Many2one(
        'attendance.kiosk', string='Signed In At', readonly=True, index=True, ondelete='set null',
    )
    out_kiosk_id = fields.Many2one(
        'attendance.kiosk', string='Signed Out At', readonly=True, ondelete='set null',
    )
    kiosk_work_location_id = fields.Many2one(
        'hr.work.location', string='Kiosk Work Location',
        compute='_compute_kiosk_work_location_id', store=True, index=True,
    )
    kiosk_transferred = fields.Boolean(
        string='Signed Out by Signing In Elsewhere', readonly=True,
        help='Signed out because the worker signed in at another kiosk.',
    )
    kiosk_offline_in = fields.Boolean(string='Signed In Offline', readonly=True)
    kiosk_offline_out = fields.Boolean(string='Signed Out Offline', readonly=True)
    # Ids of the offline kiosk events that created / closed this attendance, so
    # an event that is synced twice is only applied once.
    kiosk_event_in = fields.Char(readonly=True, copy=False, index='btree_not_null')
    kiosk_event_out = fields.Char(readonly=True, copy=False, index='btree_not_null')
    kiosk_response_ids = fields.One2many(
        'attendance.kiosk.response', 'attendance_id', string='Questionnaire Responses',
    )

    @api.depends('in_kiosk_id')
    def _compute_kiosk_work_location_id(self):
        # Keep the location the worker signed in at, even if the kiosk moves later.
        for attendance in self:
            attendance.kiosk_work_location_id = (
                attendance.kiosk_work_location_id or attendance.in_kiosk_id.work_location_id
            )
