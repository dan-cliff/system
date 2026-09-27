from odoo import fields, models


class ZooAnimalMove(models.Model):
    _name = 'zoo.animal.move'
    _description = 'Animal Move'
    _order = 'date desc, id desc'

    animal_id = fields.Many2one('zoo.animal', required=True, ondelete='cascade', index=True)
    species_id = fields.Many2one(related='animal_id.species_id', store=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    from_enclosure_id = fields.Many2one('zoo.enclosure', string='From', index=True)
    to_enclosure_id = fields.Many2one('zoo.enclosure', string='To', index=True)
    reason = fields.Char()
    user_id = fields.Many2one('res.users', string='Moved By', default=lambda self: self.env.user)
