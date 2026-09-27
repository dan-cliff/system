from odoo import fields, models


class ZooAnimalWeight(models.Model):
    _name = 'zoo.animal.weight'
    _description = 'Animal Weight'
    _order = 'date desc, id desc'

    animal_id = fields.Many2one('zoo.animal', required=True, ondelete='cascade', index=True)
    species_id = fields.Many2one(related='animal_id.species_id', store=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    weight = fields.Float(string='Weight (kg)', required=True, digits=(16, 3), aggregator='avg')
    user_id = fields.Many2one('res.users', string='Weighed By', default=lambda self: self.env.user)
    notes = fields.Char()

    _weight_positive = models.Constraint('CHECK (weight > 0)', 'Weight must be greater than zero.')
