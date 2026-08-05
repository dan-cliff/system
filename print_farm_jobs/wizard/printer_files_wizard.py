from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PrintPrinterFileWizard(models.TransientModel):
    _name = 'print.printer.file.wizard'
    _description = 'Manage Printer Cached Files'

    printer_id = fields.Many2one(
        'print.printer',
        string='Printer',
        required=True,
        readonly=True,
    )
    file_ids = fields.One2many(
        'print.printer.file.wizard.line',
        'wizard_id',
        string='Cached Files',
    )
    file_count = fields.Integer(compute='_compute_file_count', string='Files')

    @api.depends('file_ids')
    def _compute_file_count(self):
        for rec in self:
            rec.file_count = len(rec.file_ids)

    def action_refresh(self):
        self.ensure_one()
        files = self.printer_id._agent_list_files()
        self.file_ids.unlink()
        lines = []
        for f in files:
            lines.append((0, 0, {
                'wizard_id': self.id,
                'filename': f['name'],
                'size_kb': round(f.get('size', 0) / 1024, 1),
            }))
        self.file_ids = lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_delete_selected(self):
        self.ensure_one()
        selected = self.file_ids.filtered('selected')
        if not selected:
            raise UserError(_('No files selected for deletion.'))
        errors = []
        for line in selected:
            try:
                self.printer_id._agent_delete_file(line.filename)
            except Exception as e:
                errors.append('%s: %s' % (line.filename, e))
        if errors:
            raise UserError(_('Some files could not be deleted:\n%s') % '\n'.join(errors))
        return self.action_refresh()

    def action_select_all(self):
        self.file_ids.write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_deselect_all(self):
        self.file_ids.write({'selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class PrintPrinterFileWizardLine(models.TransientModel):
    _name = 'print.printer.file.wizard.line'
    _description = 'Printer Cached File'
    _order = 'filename'

    wizard_id = fields.Many2one(
        'print.printer.file.wizard',
        required=True,
        ondelete='cascade',
    )
    selected = fields.Boolean(string='Delete?', default=False)
    filename = fields.Char(string='Filename', readonly=True)
    size_kb = fields.Float(string='Size (KB)', readonly=True, digits=(10, 1))
