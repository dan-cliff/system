from odoo import fields, models


class InjuryFileNote(models.Model):
    _name = 'injury.file.note'
    _description = 'RTW File Note'
    _inherit = ['mail.thread']
    _order = 'note_date desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    note_date = fields.Date('Date', required=True, default=fields.Date.today)
    subject = fields.Char('Subject', required=True)
    author_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user, required=True)
    category = fields.Selection([
        ('correspondence', 'Correspondence'),
        ('medical',        'Medical Record'),
        ('legal',          'Legal Document'),
        ('administrative', 'Administrative'),
        ('evidence',       'Evidence / Supporting Document'),
        ('other',          'Other'),
    ], string='Category', default='administrative', required=True)
    content = fields.Text('Content / Description', required=True)
    document_reference = fields.Char('Document Reference / Number')
    is_confidential = fields.Boolean('Confidential', default=False)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_file_note_ir_attachment_rel',
        'file_note_id', 'attachment_id',
        string='Attachments',
    )
