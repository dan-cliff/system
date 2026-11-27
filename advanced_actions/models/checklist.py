from odoo import api, fields, models


class ChecklistChecklist(models.Model):
    _inherit = 'checklist.checklist'

    action_ids = fields.One2many('advanced.action', 'source_checklist_id', string='Actions')
    action_count = fields.Integer(compute='_compute_action_count')

    @api.depends('action_ids')
    def _compute_action_count(self):
        for checklist in self:
            checklist.action_count = len(checklist.action_ids)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'done':
            self.env['advanced.action']._checklists_completed(self)
        return res

