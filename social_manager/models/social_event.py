from odoo import fields, models


class SocialEvent(models.Model):
    """Special events and company releases the AI should propose posts for."""
    _name = 'social.event'
    _inherit = ['mail.thread']
    _description = 'Special Event / Release'
    _order = 'date_start, id'

    name = fields.Char(required=True, tracking=True)
    event_type_id = fields.Many2one('social.event.type', string='Type', tracking=True)
    date_start = fields.Date(string='Date', required=True, tracking=True)
    date_end = fields.Date(string='Until')
    description = fields.Text(help='What the AI should know: what is being released or celebrated, '
                                   'key messages, offers, links.')
    channel_ids = fields.Many2many('social.channel', string='Preferred Pages / Channels')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    post_ids = fields.One2many('social.post', 'event_id', string='Posts')
    post_count = fields.Integer(compute='_compute_post_count')

    def _compute_post_count(self):
        for event in self:
            event.post_count = len(event.post_ids)

    def _upcoming_domain(self, weeks=8):
        today = fields.Date.context_today(self)
        return [
            ('date_start', '<=', fields.Date.add(today, weeks=weeks)),
            '|', ('date_end', '>=', today), '&', ('date_end', '=', False), ('date_start', '>=', today),
        ]

    def _ai_summary(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'type': self.event_type_id.name or '',
            'date': self.date_start.strftime('%d/%m/%Y'),
            'until': self.date_end.strftime('%d/%m/%Y') if self.date_end else '',
            'details': self.description or '',
            'preferred_channel_ids': self.channel_ids.ids,
            'existing_post_titles': self.post_ids.mapped('name'),
        }

    def action_view_posts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_post')
        action['domain'] = [('event_id', '=', self.id)]
        action['context'] = {'default_event_id': self.id}
        return action


class SocialEventType(models.Model):
    _name = 'social.event.type'
    _description = 'Special Event Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
