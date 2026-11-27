from odoo import models


class LaserJob(models.Model):
    _name = 'laser.job'
    _inherit = ['laser.job', 'advanced.accounts.mixin']
