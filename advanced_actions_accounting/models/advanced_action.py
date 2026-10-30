from markupsafe import Markup

from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('accounting', 'Accounting')], ondelete={'accounting': 'set default'},
    )
    followup_partner_id = fields.Many2one(
        'res.partner', string='Follow-up Customer', ondelete='cascade', index='btree_not_null',
    )
    recurring_payment_id = fields.Many2one(
        'recurring.payment', string='Recurring Payment', ondelete='cascade', index='btree_not_null',
    )

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [
            ('followup_partner_id', 'accounting'), ('recurring_payment_id', 'accounting'),
        ]

    @api.model
    def _accounting_open(self, field_name, record):
        """ The open actions raised from record through field_name """
        return self.search([(field_name, '=', record.id), ('state', 'in', ('open', 'in_progress'))])

    @api.model
    def _accounting_raise(self, field_name, record, summary, note, user, date=None, merge=False):
        """ Raise an Accounting action on record, or with merge add to its open one """
        Action = self.sudo()
        if merge:
            existing = Action._accounting_open(field_name, record)[:1]
            if existing:
                existing.write({
                    'name': summary,
                    'description': (existing.description or Markup()) + Markup('<p>%s</p>') % note,
                    'user_ids': [(4, user.id)],
                })
                return existing
        deadline = fields.Datetime.to_datetime(date or fields.Date.context_today(self))
        return Action.create({
            'name': summary,
            'description': note,
            'user_ids': [(6, 0, user.ids)],
            'date_deadline': deadline,
            'source_app': 'accounting',
            field_name: record.id,
        })

    @api.model
    def _accounting_done(self, field_name, records, feedback):
        actions = self.sudo().search([
            (field_name, 'in', records.ids), ('state', 'in', ('open', 'in_progress')),
        ])
        for action in actions:
            action.message_post(body=feedback)
        actions.action_done()
