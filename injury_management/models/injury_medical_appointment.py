from odoo import fields, models


class InjuryMedicalAppointment(models.Model):
    _name = 'injury.medical.appointment'
    _description = 'Medical Appointment'
    _inherit = ['mail.thread']
    _order = 'appointment_date desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    appointment_date = fields.Datetime('Appointment Date / Time', required=True)
    appointment_type = fields.Selection([
        ('gp',            'General Practitioner'),
        ('specialist',    'Specialist'),
        ('physio',        'Physiotherapy'),
        ('psychology',    'Psychology / Counselling'),
        ('occupational',  'Occupational Therapist'),
        ('independent',   'Independent Medical Examination'),
        ('hospital',      'Hospital'),
        ('other',         'Other'),
    ], string='Appointment Type', required=True)
    provider_name = fields.Char('Provider / Practitioner Name')
    clinic_location = fields.Char('Clinic / Location')
    appointment_purpose = fields.Text('Purpose of Appointment')
    outcome = fields.Text('Outcome / Findings')
    next_appointment_date = fields.Date('Next Appointment')
    follow_up_required = fields.Boolean('Follow-up Action Required')
    follow_up_notes = fields.Text('Follow-up Notes')
    attended = fields.Boolean('Attended', default=False)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_medical_appointment_ir_attachment_rel',
        'appointment_id', 'attachment_id',
        string='Attachments',
    )
