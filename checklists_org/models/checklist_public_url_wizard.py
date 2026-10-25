# -*- coding: utf-8 -*-
from odoo import models


class ChecklistPublicUrlWizard(models.TransientModel):
    # The Organisation fields (with their cascading levels), for the link to
    # set; not scoped, and not defaulted from the user's home units.
    _name = 'checklist.public.url.wizard'
    _inherit = ['checklist.public.url.wizard', 'org.scope.mixin']
    _org_scoped = False
