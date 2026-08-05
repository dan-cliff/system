# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class zyra_rest_api_manager(models.Model):
#     _name = 'zyra_rest_api_manager.zyra_rest_api_manager'
#     _description = 'zyra_rest_api_manager.zyra_rest_api_manager'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

