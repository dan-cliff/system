from odoo import fields, models


class InjuryMedicalCertificate(models.Model):
    _name = 'injury.medical.certificate'
    _description = 'Medical Certificate'
    _inherit = ['mail.thread']
    _order = 'valid_from desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    certificate_type = fields.Selection([
        ('unfit',        'Unfit for Work'),
        ('fit_modified', 'Fit for Modified Duties'),
        ('fit_graduated','Fit for Graduated Return'),
        ('fit_full',     'Fit for Full Duties'),
        ('capacity_cert','Capacity Certificate'),
        ('other',        'Other'),
    ], string='Certificate Type', required=True)
    issue_date = fields.Date('Issue Date', required=True, default=fields.Date.today)
    valid_from = fields.Date('Valid From', required=True)
    valid_to = fields.Date('Valid To')
    doctor_name = fields.Char('Treating Doctor / Practitioner', required=True)
    clinic = fields.Char('Clinic / Practice')
    diagnosis = fields.Char('Diagnosis / Condition')
    capacity_hours = fields.Float('Approved Hours per Day', digits=(4, 1))
    restrictions = fields.Text('Restrictions / Conditions')
    notes = fields.Text('Notes')
    received_date = fields.Date('Date Received by Employer', default=fields.Date.today)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_medical_certificate_ir_attachment_rel',
        'certificate_id', 'attachment_id',
        string='Attachments',
    )
