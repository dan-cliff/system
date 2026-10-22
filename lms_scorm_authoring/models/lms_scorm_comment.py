from odoo import api, fields, models


class LmsScormComment(models.Model):
    """Review comment pinned to a slide. Never exported to the SCORM package,
    so learners never see it."""
    _name = 'lms.scorm.comment'
    _description = 'SCORM Slide Review Comment'
    _order = 'create_date desc, id desc'
    _rec_name = 'body'

    slide_id = fields.Many2one(
        'lms.scorm.slide', string='Slide', required=True, ondelete='cascade', index=True)
    course_id = fields.Many2one(
        related='slide_id.course_id', store=True, index=True, string='Course')
    company_id = fields.Many2one(related='slide_id.course_id.company_id', store=True)
    parent_id = fields.Many2one('lms.scorm.comment', string='Reply To', ondelete='cascade', index=True)
    child_ids = fields.One2many('lms.scorm.comment', 'parent_id', string='Replies')
    author_id = fields.Many2one(
        'res.users', string='Author', required=True, default=lambda self: self.env.user,
        readonly=True)
    body = fields.Text(string='Comment', required=True)
    element_id = fields.Char(string='Item', help='Slide item the comment is about, if any.')
    pos_x = fields.Float(string='Pin X (%)', help='Position of the pin across the slide.')
    pos_y = fields.Float(string='Pin Y (%)', help='Position of the pin down the slide.')
    resolved = fields.Boolean(string='Resolved', default=False, index=True)
    resolved_by_id = fields.Many2one('res.users', string='Resolved By', readonly=True)
    resolved_date = fields.Datetime(string='Resolved On', readonly=True)

    @api.depends('body')
    def _compute_display_name(self):
        for comment in self:
            text = (comment.body or '').strip().replace('\n', ' ')
            comment.display_name = text[:60] + ('…' if len(text) > 60 else '')

    def _set_resolved(self, resolved=True):
        self.write({
            'resolved': bool(resolved),
            'resolved_by_id': self.env.uid if resolved else False,
            'resolved_date': fields.Datetime.now() if resolved else False,
        })

    def action_resolve(self):
        self._set_resolved(True)

    def action_reopen(self):
        self._set_resolved(False)

    def _editor_data(self):
        self.ensure_one()
        tz_date = fields.Datetime.context_timestamp(self, self.create_date) if self.create_date else None
        return {
            'id': self.id,
            'slide_id': self.slide_id.id,
            'parent_id': self.parent_id.id or False,
            'author': self.author_id.name,
            'author_id': self.author_id.id,
            'body': self.body,
            'element_id': self.element_id or False,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'resolved': self.resolved,
            'resolved_by': self.resolved_by_id.name or '',
            'date': tz_date.strftime('%d/%m/%Y %H:%M') if tz_date else '',
        }
