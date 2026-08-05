from odoo import api, fields, models


class InjuryAddressLabelWizard(models.TransientModel):
    """Wizard for printing a Dymo 99012 mailing address label (89 × 36 mm).

    The user chooses a recipient source: the injured employee's home address,
    the insurer, the primary medical practitioner, any other contact from the
    system, or a manual entry.  Address fields are auto-populated from the
    selected source and can be overridden before printing.
    """

    _name = 'injury.address.label.wizard'
    _description = 'Mailing Address Label Wizard'

    case_id = fields.Many2one(
        'injury.rtw.case', string='RTW Case', required=True, ondelete='cascade')

    label_type = fields.Selection([
        ('employee', 'Injured Employee'),
        ('insurer',  'Insurer / WorkCover'),
        ('doctor',   'Primary Medical Practitioner'),
        ('contact',  'Other Contact'),
        ('manual',   'Manual Entry'),
    ], string='Recipient', default='employee', required=True)

    # Used when label_type == 'contact'
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
        invisible="label_type != 'contact'")

    # Address fields — editable regardless of source
    recipient_name = fields.Char('Name')
    company_name = fields.Char('Company / Organisation')
    street = fields.Char('Street')
    street2 = fields.Char('Street 2')
    city = fields.Char('City / Suburb')
    state_id = fields.Many2one('res.country.state', string='State / Province')
    zip_code = fields.Char('ZIP / Postcode')
    country_id = fields.Many2one('res.country', string='Country')

    @api.onchange('case_id', 'label_type', 'partner_id')
    def _onchange_fill_address(self):
        """Auto-populate address fields from the selected recipient source."""
        partner = None

        if self.label_type == 'employee':
            emp = self.case_id.employee_id
            if emp and emp.address_home_id:
                partner = emp.address_home_id
            elif emp:
                # No private address — use employee name + company work address
                self.recipient_name = emp.name
                self.company_name = self.env.company.name
                self.street = ''
                self.street2 = ''
                self.city = ''
                self.state_id = False
                self.zip_code = ''
                self.country_id = False
                return

        elif self.label_type == 'insurer':
            partner = self.case_id.insurer_id

        elif self.label_type == 'doctor':
            partner = self.case_id.primary_doctor_id

        elif self.label_type == 'contact':
            partner = self.partner_id

        if partner:
            self._fill_from_partner(partner)

    def _fill_from_partner(self, partner):
        """Copy address fields from a res.partner record."""
        self.recipient_name = partner.name or ''
        self.company_name = (
            partner.parent_id.name
            if partner.parent_id
            else (partner.company_name or '')
        )
        self.street = partner.street or ''
        self.street2 = partner.street2 or ''
        self.city = partner.city or ''
        self.state_id = partner.state_id
        self.zip_code = partner.zip or ''
        self.country_id = partner.country_id

    def action_print(self):
        """Generate the Dymo address label PDF."""
        self.ensure_one()
        return (
            self.env.ref('injury_management.action_report_address_label')
            .report_action(self)
        )
