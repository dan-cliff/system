from odoo import _, fields, models


class RecurringPayment(models.Model):
    _inherit = 'recurring.payment'

    action_ids = fields.One2many('advanced.action', 'recurring_payment_id', string='Actions')
    action_open_count = fields.Integer(compute='_compute_action_open_count')

    def _compute_action_open_count(self):
        for record in self:
            record.action_open_count = len(
                record.action_ids.filtered(lambda action: action.state in ('open', 'in_progress'))
            )

    def _raise_failure_action(self, summary, note, user):
        self.ensure_one()
        if not self.env['advanced.action']._accounting_open('recurring_payment_id', self):
            self.env['advanced.action']._accounting_raise('recurring_payment_id', self, summary, note, user)

    def _close_failure_activities(self):
        super()._close_failure_activities()
        solved = self.filtered(lambda rec: not rec.has_error)
        self.env['advanced.action']._accounting_done(
            'recurring_payment_id', solved, _('The payments are created again.'))

    def action_open_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'domain': [('recurring_payment_id', '=', self.id)],
            'context': {'default_recurring_payment_id': self.id, 'default_source_app': 'accounting',
                        'search_default_open': 1},
        }
