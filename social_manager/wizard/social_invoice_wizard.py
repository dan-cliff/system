from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class SocialInvoiceWizard(models.TransientModel):
    _name = 'social.invoice.wizard'
    _description = 'Invoice Monetised Content'

    def _default_date_to(self):
        return fields.Date.context_today(self).replace(day=1) - timedelta(days=1)

    def _default_date_from(self):
        return self._default_date_to().replace(day=1)

    date_from = fields.Date(string='From', required=True, default=_default_date_from)
    date_to = fields.Date(string='To', required=True, default=_default_date_to)
    platform_ids = fields.Many2many(
        'social.platform', string='Platforms', domain="[('is_monetised', '=', True)]",
        default=lambda self: self.env['social.platform'].search([('is_monetised', '=', True)]),
        help='One invoice is created per Platform, with a line per Page / Channel.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    integrate_accounts = fields.Boolean(compute='_compute_integrate_accounts')

    def _compute_integrate_accounts(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param('social_manager.integrate_accounts') in ('True', '1')
        for wizard in self:
            wizard.integrate_accounts = enabled

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError('The From date must be before the To date.')

    def action_create(self):
        self.ensure_one()
        if not self.integrate_accounts:
            raise UserError('Turn on "Integrate to Accounts" in Settings > Social Manager first.')
        invoices = self.env['social.invoice']._create_invoices(
            self.date_from, self.date_to, self.platform_ids, self.company_id)
        if not invoices:
            raise UserError('There is no uninvoiced monetised income for these Platforms between %s and %s.' % (
                self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y')))
        action = self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_invoice')
        action['domain'] = [('id', 'in', invoices.ids)]
        return action
