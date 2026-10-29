from odoo import models


class EmbroideryJob(models.Model):
    _name = 'embroidery.job'
    _inherit = ['embroidery.job', 'advanced.accounts.mixin']


class EmbroideryDesign(models.Model):
    _name = 'embroidery.design'
    _inherit = ['embroidery.design', 'advanced.accounts.mixin']
