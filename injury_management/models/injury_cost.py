from odoo import fields, models


class InjuryCost(models.Model):
    _name = 'injury.cost'
    _description = 'RTW Case Cost'
    _inherit = ['mail.thread']
    _order = 'cost_date desc'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    cost_date = fields.Date('Date', required=True, default=fields.Date.today)
    cost_type = fields.Selection([
        ('medical',        'Medical / Treatment'),
        ('rehabilitation', 'Rehabilitation'),
        ('legal',          'Legal'),
        ('wages',          'Wages / Compensation'),
        ('admin',          'Administrative'),
        ('travel',         'Travel'),
        ('equipment',      'Equipment / Aids'),
        ('other',          'Other'),
    ], string='Cost Type', required=True)
    description = fields.Char('Description', required=True)
    payee = fields.Char('Payee / Provider')
    invoice_reference = fields.Char('Invoice / Reference Number')
    amount = fields.Monetary('Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    reimbursed = fields.Boolean('Reimbursed / Claimed')
    reimbursement_date = fields.Date('Reimbursement Date')
    notes = fields.Text('Notes')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_cost_ir_attachment_rel',
        'cost_id', 'attachment_id',
        string='Attachments',
    )
