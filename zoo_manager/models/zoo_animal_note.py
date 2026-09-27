from odoo import fields, models


class ZooAnimalNote(models.Model):
    _name = 'zoo.animal.note'
    _description = 'Animal Note'
    _order = 'date desc, id desc'
    _rec_name = 'summary'

    animal_id = fields.Many2one('zoo.animal', required=True, ondelete='cascade', index=True)
    species_id = fields.Many2one(related='animal_id.species_id', store=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user)
    summary = fields.Char(required=True)
    note = fields.Html()
