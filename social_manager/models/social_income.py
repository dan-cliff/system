from odoo import api, fields, models
from odoo.exceptions import UserError


class SocialIncome(models.Model):
    """Income earned from monetised content - per post where known, otherwise per Page / Channel."""
    _name = 'social.income'
    _description = 'Social Monetisation Income'
    _order = 'date desc, id desc'

    name = fields.Char(string='Description', required=True)
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    income_type_id = fields.Many2one('social.income.type', string='Income Type')
    channel_id = fields.Many2one('social.channel', string='Page / Channel', required=True, index=True,
                                 domain="[('is_monetised', '=', True)]")
    platform_id = fields.Many2one(related='channel_id.platform_id', store=True, string='Platform', index=True)
    publication_id = fields.Many2one('social.post.publication', string='Published Post', index=True,
                                     domain="[('channel_id', '=', channel_id)]")
    post_id = fields.Many2one(related='publication_id.post_id', store=True, string='Post', index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    external_ref = fields.Char(string='Platform Reference', readonly=True, index=True,
                               help='Set on income imported from the platform, so it is not imported twice.')
    invoice_line_id = fields.Many2one('social.invoice.line', string='Invoice Line', readonly=True,
                                      ondelete='set null', copy=False)
    social_invoice_id = fields.Many2one(related='invoice_line_id.invoice_id', string='Monetisation Invoice')
    move_id = fields.Many2one(related='invoice_line_id.invoice_id.move_id', string='Invoice')
    invoiced = fields.Boolean(compute='_compute_invoiced', store=True)

    @api.depends('invoice_line_id')
    def _compute_invoiced(self):
        for income in self:
            income.invoiced = bool(income.invoice_line_id)

    @api.onchange('publication_id')
    def _onchange_publication_id(self):
        if self.publication_id:
            self.channel_id = self.publication_id.channel_id

    def write(self, vals):
        protected = {'amount', 'date', 'channel_id', 'company_id'}
        if protected & set(vals) and self.filtered('invoice_line_id'):
            raise UserError('Income that has been invoiced can no longer be changed.')
        return super().write(vals)

    def unlink(self):
        if self.filtered('invoice_line_id'):
            raise UserError('Income that has been invoiced can not be deleted.')
        return super().unlink()

    @api.model
    def _import_rows(self, channel, rows):
        """Create income from provider rows ({ref, date, amount, publication_external_id, name})."""
        for row in rows or []:
            if not row.get('amount') or (row.get('ref') and self.search_count(
                    [('channel_id', '=', channel.id), ('external_ref', '=', row['ref'])], limit=1)):
                continue
            publication = self.env['social.post.publication']
            if row.get('publication_external_id'):
                publication = publication.search([
                    ('channel_id', '=', channel.id), ('external_id', '=', row['publication_external_id'])], limit=1)
            self.create({
                'name': row.get('name') or 'Monetisation income',
                'date': row['date'],
                'amount': row['amount'],
                'channel_id': channel.id,
                'publication_id': publication.id,
                'external_ref': row.get('ref'),
                'income_type_id': self.env.ref('social_manager.income_type_ad_revenue', raise_if_not_found=False).id,
                'company_id': channel.company_id.id,
            })
