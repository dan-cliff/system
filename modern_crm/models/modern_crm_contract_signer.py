import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

# A signer's progress: the signing portal depends on these values.
SIGNER_STATES = [
    ('draft', 'Not Sent'),
    ('waiting', 'Waiting for Others'),
    ('sent', 'Awaiting Signature'),
    ('signed', 'Signed'),
    ('declined', 'Declined'),
    ('cancelled', 'Cancelled'),
]


class ModernCrmContractSigner(models.Model):
    _name = 'modern.crm.contract.signer'
    _description = 'CRM Contract Signer'
    _order = 'contract_id, sequence, id'

    contract_id = fields.Many2one(
        'modern.crm.contract', string='Contract', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    sequence = fields.Integer(
        'Signing Order', default=10,
        help='Signers sign in this order; signers with the same number are asked at the same time.')
    partner_id = fields.Many2one('res.partner', string='Signer', required=True)
    email = fields.Char(related='partner_id.email')
    role = fields.Char('Signs As', help='E.g. Customer, Director, For Our Company.')
    state = fields.Selection(SIGNER_STATES, string='Status', default='draft', required=True, copy=False)
    access_token = fields.Char(copy=False, groups='base.group_system')
    sent_on = fields.Datetime('Requested On', readonly=True, copy=False)
    signed_on = fields.Datetime('Signed On', readonly=True, copy=False)
    signed_by = fields.Char('Signed As', readonly=True, copy=False,
                            help='The name the signer typed when signing.')
    signature = fields.Image('Signature', readonly=True, copy=False, attachment=True, max_width=1024,
                             max_height=1024)
    signer_ip = fields.Char('Signed From (IP)', readonly=True, copy=False)
    decline_reason = fields.Text('Decline Reason', readonly=True, copy=False)
    sign_url = fields.Char('Signing Link', compute='_compute_sign_url', groups='base.group_system')

    def _compute_sign_url(self):
        for signer in self:
            signer.sign_url = signer.sudo()._get_sign_url() if signer.access_token else False

    def _get_sign_url(self):
        self.ensure_one()
        base_url = self.contract_id.get_base_url()
        return f'{base_url}/crm/contract/sign/{self.id}/{self.access_token}'

    def _reset_signature(self, state='waiting'):
        for signer in self.sudo():
            signer.write({
                'state': state,
                'access_token': uuid.uuid4().hex if state == 'waiting' else False,
                'sent_on': False, 'signed_on': False, 'signed_by': False, 'signature': False,
                'signer_ip': False, 'decline_reason': False,
            })

    def _send_request(self):
        template = self.env.ref('modern_crm.mail_template_contract_signature_request').sudo()
        for signer in self.sudo():
            signer.write({'state': 'sent', 'sent_on': fields.Datetime.now()})
            template.send_mail(signer.id, email_layout_xmlid='mail.mail_notification_light')
            signer.contract_id.message_post(
                body=self.env._('Signature requested from %s.', signer.partner_id.display_name))

    def _format_signed_on(self):
        """The signing time in the signer's own time zone, as dd/mm/yyyy HH:MM."""
        self.ensure_one()
        if not self.signed_on:
            return ''
        tz_env = self.with_context(tz=self.partner_id.tz or self.contract_id.user_id.tz or 'UTC')
        return fields.Datetime.context_timestamp(tz_env, self.signed_on).strftime('%d/%m/%Y %H:%M')

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        if any(signer.state == 'signed' and signer.contract_id.state != 'draft' for signer in self):
            raise UserError(self.env._('A signer who has signed cannot be removed.'))
