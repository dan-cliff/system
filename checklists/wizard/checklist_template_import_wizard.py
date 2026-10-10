# -*- coding: utf-8 -*-
import base64

from odoo import fields, models


class ChecklistTemplateImportWizard(models.TransientModel):
    _name = 'checklist.template.import.wizard'
    _description = 'Import Checklist Templates'

    # Set when opened from a template: the file's questions go into it.
    template_id = fields.Many2one('checklist.template', string='Template', readonly=True)
    file = fields.Binary(string='File', required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        content = base64.b64decode(self.file)
        if self.template_id:
            self.template_id._import_into(content)
            return {'type': 'ir.actions.act_window_close'}
        templates = self.env['checklist.template']._import_file(content)
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._('Imported Templates'),
            'res_model': 'checklist.template',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', templates.ids)],
        }
        if len(templates) == 1:
            action.update(view_mode='form', views=[(False, 'form')], res_id=templates.id)
        return action
