"""The option lists of Subscriptions, under Configuration (see CLAUDE.md >
Choice fields): stages, tags and close reasons."""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleSubscriptionStage(models.Model):
    _name = 'sale.subscription.stage'
    _description = 'Subscription Stage'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean(string='Folded in Kanban')
    description = fields.Text(translate=True)
    # technical: the code acts on the type of a stage
    type = fields.Selection([
        ('draft', 'Draft'),
        ('pre', 'Ready to Start'),
        ('in_progress', 'In Progress'),
        ('post', 'Closed'),
    ], string='Type', default='pre', required=True,
        help="Draft: being prepared.\n"
             "Ready to Start: started by the scheduled action on its start date.\n"
             "In Progress: invoiced on its invoice dates.\n"
             "Closed: ended (only one stage can be of this type).")
    # kept for the stages of the Subscription management app; the type decides
    in_progress = fields.Boolean(string='In Progress')

    @api.constrains('type', 'active')
    def _check_single_closed_stage(self):
        if self.search_count([('type', '=', 'post')]) > 1:
            raise ValidationError(self.env._('There can only be one stage of the Closed type.'))


class SaleSubscriptionTag(models.Model):
    _name = 'sale.subscription.tag'
    _description = 'Subscription Tag'
    _order = 'name, id'

    name = fields.Char(string='Tag Name', required=True)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True)


class SaleSubscriptionCloseReason(models.Model):
    _name = 'sale.subscription.close.reason'
    _description = 'Subscription Close Reason'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
