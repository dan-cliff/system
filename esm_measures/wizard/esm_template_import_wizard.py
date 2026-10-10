# -*- coding: utf-8 -*-
import base64

from odoo import fields, models
from odoo.exceptions import UserError


class EsmTemplateImportWizard(models.TransientModel):
    _name = 'esm.template.import.wizard'
    _description = 'Import Inspection Templates'

    # Technical: the template model the wizard was opened from.
    template_model = fields.Char(required=True)
    file = fields.Binary(string='JSON File', required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        Templates = self.env[self.template_model]
        if not isinstance(Templates, self.env.registry['esm.template.mixin']):
            raise UserError(self.env._('Templates cannot be imported here.'))
        templates = Templates._import_json(base64.b64decode(self.file))
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._('Imported Templates'),
            'res_model': Templates._name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', templates.ids)],
        }
        if len(templates) == 1:
            action.update(view_mode='form', res_id=templates.id)
        return action
