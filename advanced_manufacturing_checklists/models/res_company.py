# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mrp_qa_checklist_group_ids = fields.Many2many(
        'checklist.group', 'res_company_mrp_qa_checklist_group_rel', 'company_id', 'group_id',
        string='QA Checklist Groups',
        help="Templates in these Checklist Groups can be started as QA checks on the Work Centre app.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mrp_qa_checklist_group_ids = fields.Many2many(
        related='company_id.mrp_qa_checklist_group_ids', readonly=False,
    )
