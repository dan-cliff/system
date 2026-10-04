from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HelpSchedulePublishWizard(models.TransientModel):
    _name = 'help.schedule.publish.wizard'
    _description = 'Schedule Article Publish'

    article_id = fields.Many2one(
        'help.article', string='Article', required=True, ondelete='cascade',
    )
    article_name = fields.Char(related='article_id.name', string='Article Title', readonly=True)
    publish_date = fields.Datetime(
        'Publish At',
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(hours=1),
        help='The article will be automatically published within one hour of this date/time.',
    )
    current_publish_date = fields.Datetime(
        related='article_id.publish_date',
        string='Currently Scheduled For',
        readonly=True,
    )
    has_existing_schedule = fields.Boolean(compute='_compute_has_existing_schedule')

    @api.depends('current_publish_date')
    def _compute_has_existing_schedule(self):
        for rec in self:
            rec.has_existing_schedule = bool(rec.current_publish_date)

    @api.constrains('publish_date')
    def _check_publish_date(self):
        for rec in self:
            if rec.publish_date and rec.publish_date <= fields.Datetime.now():
                raise ValidationError(_('The scheduled date must be in the future.'))

    def action_schedule(self):
        self.ensure_one()
        self.article_id.publish_date = self.publish_date
        return {'type': 'ir.actions.act_window_close'}

    def action_clear_schedule(self):
        self.ensure_one()
        self.article_id.publish_date = False
        return {'type': 'ir.actions.act_window_close'}
