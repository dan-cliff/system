from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    print3d_estimate_ids = fields.Many2many(
        'print3d.estimate',
        string='3D Print Costings',
        compute='_compute_print3d_estimate_ids',
    )
    print3d_estimate_count = fields.Integer(compute='_compute_print3d_estimate_ids')
    print3d_line_ids = fields.Many2many(
        'account.move.line',
        string='3D Print Lines',
        compute='_compute_print3d_estimate_ids',
    )
    print3d_cost_total = fields.Monetary(
        string='3D Print Cost',
        compute='_compute_print3d_estimate_ids',
        help='Total recorded cost (filament, printer time and fees) of the 3D prints on this invoice.',
    )

    @api.depends('invoice_line_ids.print3d_estimate_id', 'invoice_line_ids.quantity')
    def _compute_print3d_estimate_ids(self):
        for move in self:
            lines = move.invoice_line_ids.filtered('print3d_estimate_id')
            move.print3d_line_ids = lines
            move.print3d_estimate_ids = lines.print3d_estimate_id
            move.print3d_estimate_count = len(lines.print3d_estimate_id)
            move.print3d_cost_total = sum(
                line.print3d_estimate_id.currency_id._convert(
                    line.print3d_estimate_id.cost_total * line.quantity,
                    move.currency_id,
                    move.company_id,
                    move.invoice_date or fields.Date.context_today(move),
                )
                for line in lines
            )

    def action_view_print3d_estimates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('3D Print Costings'),
            'res_model': 'print3d.estimate',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.print3d_estimate_ids.ids)],
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    print3d_estimate_id = fields.Many2one(
        'print3d.estimate',
        string='3D Print Estimate',
        index='btree_not_null',
        copy=True,
        readonly=True,
    )
    print3d_filament_count = fields.Integer(related='print3d_estimate_id.filament_count', string='Filaments')
    print3d_filament_g = fields.Float(related='print3d_estimate_id.total_filament_g', string='Filament (g)')
    print3d_print_time = fields.Char(related='print3d_estimate_id.print_time_display', string='Print Time')
    print3d_material_cost = fields.Monetary(
        related='print3d_estimate_id.material_cost', string='Filament Cost',
        currency_field='print3d_currency_id',
    )
    print3d_machine_cost = fields.Monetary(
        related='print3d_estimate_id.machine_cost', string='Printer Time Cost',
        currency_field='print3d_currency_id',
    )
    print3d_setup_cost = fields.Monetary(
        related='print3d_estimate_id.setup_cost', string='Setup & Colour Fees',
        currency_field='print3d_currency_id',
    )
    print3d_cost_total = fields.Monetary(
        related='print3d_estimate_id.cost_total', string='Cost per Print',
        currency_field='print3d_currency_id',
    )
    print3d_currency_id = fields.Many2one(related='print3d_estimate_id.currency_id', string='3D Print Currency')
