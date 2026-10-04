import uuid
from odoo import api, fields, models


class HelpChatbotSession(models.Model):
    _name = 'help.chatbot.session'
    _description = 'Help Centre Chat Session'
    _order = 'create_date desc'

    name = fields.Char('Session', compute='_compute_name')
    session_token = fields.Char(
        'Session Token', index=True, copy=False,
        default=lambda self: str(uuid.uuid4()),
    )
    user_id = fields.Many2one(
        'res.users', 'User', ondelete='set null',
        help='Set when the visitor is an authenticated user.',
    )
    visitor_ip = fields.Char('Visitor IP', readonly=True)
    message_ids = fields.One2many('help.chatbot.message', 'session_id', 'Messages')
    message_count = fields.Integer('Message Count', compute='_compute_message_count')

    @api.depends('create_date', 'user_id')
    def _compute_name(self):
        for rec in self:
            user = rec.user_id.name or 'Anonymous'
            date = rec.create_date.strftime('%d/%m/%Y %H:%M') if rec.create_date else ''
            rec.name = f'{user} — {date}'

    def _compute_message_count(self):
        data = self.env['help.chatbot.message'].read_group(
            [('session_id', 'in', self.ids)],
            ['session_id'],
            ['session_id'],
        )
        counts = {d['session_id'][0]: d['session_id_count'] for d in data}
        for rec in self:
            rec.message_count = counts.get(rec.id, 0)


class HelpChatbotMessage(models.Model):
    _name = 'help.chatbot.message'
    _description = 'Help Centre Chat Message'
    _order = 'id asc'

    session_id = fields.Many2one(
        'help.chatbot.session', 'Session',
        required=True, ondelete='cascade', index=True,
    )
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ], required=True)
    content = fields.Text('Content', required=True)
    article_ids = fields.Many2many(
        'help.article', string='Referenced Articles',
        help='Articles that were surfaced for this message.',
    )
