from odoo import fields, models


class ZooHealthRecord(models.Model):
    _name = 'zoo.health.record'
    _description = 'Health Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'summary'

    animal_id = fields.Many2one('zoo.animal', required=True, ondelete='cascade', index=True, tracking=True)
    species_id = fields.Many2one(related='animal_id.species_id', store=True)
    enclosure_id = fields.Many2one(related='animal_id.enclosure_id')
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    record_type_id = fields.Many2one(
        'zoo.health.record.type', string='Type', required=True, tracking=True,
        default=lambda self: self.env.ref('zoo_manager.zoo_health_record_type_checkup', raise_if_not_found=False),
    )
    summary = fields.Char(required=True, tracking=True)
    veterinarian = fields.Char(help='Vet who carried out the visit or treatment.')
    user_id = fields.Many2one('res.users', string='Recorded By', default=lambda self: self.env.user)
    diagnosis = fields.Text()
    treatment = fields.Text()
    medication = fields.Text(help='Medication, dose and duration.')
    follow_up_date = fields.Date(tracking=True)
    state = fields.Selection(
        [('open', 'Ongoing'), ('closed', 'Resolved')],
        default='open', required=True, tracking=True,
    )

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reopen(self):
        self.write({'state': 'open'})
