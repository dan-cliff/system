from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


class MandrillReplyRoute(models.Model):
    """Reply-to address used for emails sent from a given model through
    Mailchimp Transactional, e.g. invoices reply to accounts@."""
    _name = 'mandrill.reply.route'
    _description = 'Mailchimp Transactional Reply-To Address'
    _order = 'sequence, id'
    _rec_name = 'model_id'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', 'Sent From', required=True, ondelete='cascade',
        domain=[('is_mail_thread', '=', True), ('transient', '=', False)],
        help="Emails sent from records of this model use this reply-to address.")
    model = fields.Char(related='model_id.model', store=True, index=True)
    alias_id = fields.Many2one(
        'mail.alias', 'Alias', ondelete='restrict',
        help="Reply to this Odoo alias. Leave empty to type an address instead.")
    email = fields.Char(
        'Email Address',
        help="Reply-to address when no alias is selected, e.g. accounts@example.com.")
    reply_to = fields.Char('Reply-To', compute='_compute_reply_to', store=True)
    company_id = fields.Many2one(
        'res.company', 'Company',
        help="Only use this address for emails sent by this company. Leave empty for all companies.")

    _model_company_uniq = models.Constraint(
        'unique(model_id, company_id)',
        'There is already a reply-to address for this model and company.',
    )

    @api.depends('alias_id.alias_full_name', 'email')
    def _compute_reply_to(self):
        for route in self:
            route.reply_to = (route.alias_id.alias_full_name if route.alias_id else (route.email or '').strip()) or False

    @api.constrains('alias_id', 'email')
    def _check_reply_to(self):
        for route in self:
            if not route.alias_id and not email_normalize(route.email or ''):
                raise ValidationError(_("Select an alias or enter a valid email address for %s.", route.model_id.name))

    @api.model
    def _find_for_model(self, model, company=None):
        """Reply-to rule for ``model``; a company-specific rule wins over one
        for all companies."""
        if not model:
            return self.browse()
        company = company or self.env.company
        routes = self.search([('model', '=', model), ('company_id', 'in', [company.id, False])])
        return routes.filtered('company_id')[:1] or routes[:1]

    @api.model_create_multi
    def create(self, vals_list):
        routes = super().create(vals_list)
        self.env['mandrill.service']._schedule_route_sync()
        return routes

    def write(self, vals):
        res = super().write(vals)
        self.env['mandrill.service']._schedule_route_sync()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['mandrill.service']._schedule_route_sync()
        return res
