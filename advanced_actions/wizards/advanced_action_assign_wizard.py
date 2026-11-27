from odoo import api, fields, models
from odoo.exceptions import UserError


class AdvancedActionAssignWizard(models.TransientModel):
    """Give several users an action each, e.g. each completing their own
    copy of a checklist. (Assigned To on an action is for one action that
    any of its users can complete.)"""
    _name = 'advanced.action.assign.wizard'
    _description = 'Create an Action for Each User'

    origin_id = fields.Many2one('advanced.action', string='Duplicate Of', readonly=True)
    user_ids = fields.Many2many(
        'res.users', string='Users', required=True, domain=[('share', '=', False)],
        help='Each of these users gets their own action.',
    )
    name = fields.Char(string='Title', required=True)
    description = fields.Html()
    date_deadline = fields.Datetime(string='Due At')
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Important'), ('2', 'Very Important'), ('3', 'Critical')],
        default='0',
    )
    checklist_template_id = fields.Many2one('checklist.template', string='Required Checklist')
    tag_ids = fields.Many2many('advanced.action.tag', string='Tags')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        origin = self.env['advanced.action'].browse(res.get('origin_id')).exists()
        if origin:
            res.update({
                'name': origin.name,
                'description': origin.description,
                'date_deadline': origin.date_deadline,
                'priority': origin.priority,
                'checklist_template_id': origin.checklist_template_id.id,
                'tag_ids': [(6, 0, origin.tag_ids.ids)],
            })
        return res

    def _action_vals(self, user):
        return {
            'name': self.name,
            'description': self.description,
            'date_deadline': self.date_deadline,
            'priority': self.priority,
            'checklist_template_id': self.checklist_template_id.id,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'user_ids': [(6, 0, user.ids)],
        }

    def action_create(self):
        self.ensure_one()
        if not self.user_ids:
            raise UserError(self.env._('Choose at least one user.'))
        Action = self.env['advanced.action']
        actions = Action
        for user in self.user_ids:
            vals = self._action_vals(user)
            if self.origin_id:
                # Copies keep the record the original was raised from.
                actions |= self.origin_id.copy(dict(vals, origin_id=self.origin_id.id))
            else:
                actions |= Action.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,form',
            'domain': [('id', 'in', actions.ids)],
        }
