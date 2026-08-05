from odoo import fields, models


class InjuryCaseNote(models.Model):
    _name = 'injury.case.note'
    _description = 'RTW Case Note'
    _inherit = ['mail.thread']
    _order = 'note_date desc, id desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    note_date = fields.Date('Date', required=True, default=fields.Date.today)
    note_type = fields.Selection([
        ('general',       'General Note'),
        ('medical',       'Medical Update'),
        ('rtw_progress',  'RTW Progress'),
        ('employer',      'Employer Communication'),
        ('insurer',       'Insurer Communication'),
        ('legal',         'Legal'),
        ('other',         'Other'),
    ], string='Note Type', default='general', required=True)
    author_id = fields.Many2one(
        'res.users', string='Author', default=lambda self: self.env.user, required=True)
    content = fields.Text('Note Content', required=True)
    is_confidential = fields.Boolean('Confidential', default=False)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_case_note_ir_attachment_rel',
        'note_id', 'attachment_id',
        string='Attachments',
    )
