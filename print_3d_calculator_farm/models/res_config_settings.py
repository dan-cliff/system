from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    print3d_consume_on_done = fields.Boolean(
        string='Consume Filament on Completion',
        config_parameter='print_3d_calculator_farm.consume_on_done',
        help='When a print job is marked as done, take the filament it used out of '
             'stock (from each material\'s filament product).',
    )
