from odoo import api, fields, models


class RiskAssessmentLine(models.Model):
    _inherit = 'risk.assessment.line'

    bowtie_threat_ids = fields.One2many(
        'risk.bowtie.threat', 'assessment_line_id', string='Threats', copy=True,
    )
    bowtie_consequence_ids = fields.One2many(
        'risk.bowtie.consequence', 'assessment_line_id', string='Consequences', copy=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        # A risk pulled in from a Risk Template brings the template risk's bowtie with it.
        TemplateLine = self.env['risk.template.line']
        for vals in vals_list:
            if vals.get('source_template_line_id') and not any(
                key in vals for key in ('bowtie_hazard', 'bowtie_threat_ids', 'bowtie_consequence_ids')
            ):
                vals.update(TemplateLine.browse(vals['source_template_line_id'])._bowtie_copy_vals())
        return super().create(vals_list)
