from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Contacts get the Organisation fields automatically (ir_model_fields.py);
    # a contact created under a company takes the company's Organisation.
    _org_parent_field = 'parent_id'
