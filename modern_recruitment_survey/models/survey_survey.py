# -*- coding: utf-8 -*-
from odoo import fields, models


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    # Recruitment's survey type, labelled Talent.
    survey_type = fields.Selection(selection_add=[('recruitment', 'Talent')], ondelete={'recruitment': 'set default'})
