# -*- coding: utf-8 -*-
from odoo import api, models

from odoo.addons.org_structure.models.org_scope_mixin import ORG_LEVELS


class ChecklistTemplate(models.Model):
    _inherit = 'checklist.template'

    # Public submission (see checklists/models/checklist_public.py): a signed
    # link can set the checklist's Organisation units.

    @api.model
    def _public_link_record_fields(self):
        return dict(super()._public_link_record_fields(), **{level: f'org_{level}_id' for level in ORG_LEVELS})

    def _public_link_record(self, field_name, record):
        for level in ORG_LEVELS:
            if field_name == f'org_{level}_id':
                return self.env['org.config']._is_enabled(level)
        return super()._public_link_record(field_name, record)
