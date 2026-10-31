# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RosteringApplyTemplateWizard(models.TransientModel):
    _name = 'rostering.apply.template.wizard'
    _description = 'Apply Roster Template'

    roster_id = fields.Many2one('rostering.roster', string='Roster', required=True, ondelete='cascade')
    template_id = fields.Many2one(
        'rostering.template', string='Roster Template', required=True, ondelete='cascade',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(related='roster_id.company_id')
    replace = fields.Boolean(string='Replace Existing Shifts',
                             help='Remove the roster\'s current shifts before adding the template\'s.')
    shift_count = fields.Integer(related='roster_id.shift_count')
    cycle_mismatch = fields.Boolean(compute='_compute_cycle_mismatch')

    @api.depends('roster_id.cycle', 'template_id.cycle')
    def _compute_cycle_mismatch(self):
        for wizard in self:
            wizard.cycle_mismatch = bool(wizard.template_id) and wizard.template_id.cycle != wizard.roster_id.cycle

    def action_apply(self):
        self.ensure_one()
        self.roster_id._apply_template(self.template_id, replace=self.replace)
        return {'type': 'ir.actions.act_window_close'}
