from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    wildlife_license_number = fields.Char(string='Wildlife License Number', tracking=True)
    jurisdiction_ids = fields.Many2many(
        'res.country.state', 'res_partner_zoo_jurisdiction_rel', 'partner_id', 'state_id',
        string='Jurisdiction', help='States or territories the wildlife license covers.',
    )
    zoo_animal_sold_ids = fields.One2many('zoo.animal', 'seller_id', string='Animals Sold')
