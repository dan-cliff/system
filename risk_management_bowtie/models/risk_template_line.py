from odoo import fields, models


class RiskTemplateLine(models.Model):
    _inherit = 'risk.template.line'

    bowtie_threat_ids = fields.One2many(
        'risk.bowtie.threat', 'template_line_id', string='Threats', copy=True,
    )
    bowtie_consequence_ids = fields.One2many(
        'risk.bowtie.consequence', 'template_line_id', string='Consequences', copy=True,
    )
