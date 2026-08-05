from odoo import fields, models


class InjuryMeeting(models.Model):
    _name = 'injury.meeting'
    _description = 'RTW Meeting / Communication'
    _inherit = ['mail.thread']
    _order = 'meeting_date desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    meeting_date = fields.Datetime('Date / Time', required=True, default=fields.Datetime.now)
    meeting_type = fields.Selection([
        ('rtw_meeting',    'RTW Meeting'),
        ('case_conference','Case Conference'),
        ('phone_call',     'Phone Call'),
        ('email',          'Email'),
        ('letter',         'Letter / Correspondence'),
        ('site_visit',     'Site Visit'),
        ('other',          'Other'),
    ], string='Type', required=True)
    subject = fields.Char('Subject', required=True)
    participants = fields.Text('Participants / Attendees')
    location = fields.Char('Location / Medium')
    summary = fields.Text('Summary / Minutes')
    action_items = fields.Text('Action Items')
    next_meeting_date = fields.Date('Next Meeting / Follow-up Date')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_meeting_ir_attachment_rel',
        'meeting_id', 'attachment_id',
        string='Attachments',
    )
