# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Fields the automatic fill (e.g. from Attendances) owns on automatic entries.
AUTO_FIELDS = {'sheet_id', 'date', 'unit_amount', 'is_auto'}


class AdvancedTimesheetLine(models.Model):
    _name = 'advanced.timesheet.line'
    _description = 'Timesheet Entry'
    _order = 'date, id'

    sheet_id = fields.Many2one(
        'advanced.timesheet', string='Timesheet', required=True, index=True, ondelete='cascade',
    )
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, index=True)
    project_id = fields.Many2one('project.project', string='Project', index=True)
    task_id = fields.Many2one(
        'project.task', string='Task', index=True,
        domain="[('project_id', '=?', project_id)]",
    )
    name = fields.Char(string='Description')
    unit_amount = fields.Float(string='Hours', default=0.0)
    is_auto = fields.Boolean(
        string='Automatic', readonly=True, copy=False,
        help='Filled in automatically (e.g. from Attendances): the date and hours follow their source.',
    )
    user_id = fields.Many2one(related='sheet_id.user_id', store=True, index=True)
    person_name = fields.Char(related='sheet_id.person_name')
    state = fields.Selection(related='sheet_id.state')
    company_id = fields.Many2one(related='sheet_id.company_id', store=True, index=True)

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id.project_id:
            self.project_id = self.task_id.project_id

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False

    @api.constrains('date', 'sheet_id')
    def _check_date(self):
        for line in self:
            if not line.sheet_id.date_start <= line.date <= line.sheet_id.date_end:
                raise ValidationError(_(
                    '%(day)s is outside the timesheet\'s period (%(start)s – %(end)s).',
                    day=line.date.strftime('%d/%m/%Y'),
                    start=line.sheet_id.date_start.strftime('%d/%m/%Y'),
                    end=line.sheet_id.date_end.strftime('%d/%m/%Y'),
                ))

    @api.constrains('unit_amount')
    def _check_unit_amount(self):
        if any(line.unit_amount < 0 for line in self):
            raise ValidationError(_('Hours cannot be negative.'))

    def _is_sync(self):
        return self.env.context.get('advanced_timesheet_sync')

    def _check_editable(self, vals=None):
        if self._is_sync():
            return
        if any(line.sheet_id.state != 'draft' for line in self):
            raise UserError(_('Submitted timesheets cannot be changed. Reset it to draft first.'))
        if vals is None or AUTO_FIELDS & set(vals):
            if any(line.is_auto for line in self):
                raise UserError(_('The date and hours of an automatic entry follow its source '
                                  '(e.g. the attendance) and cannot be changed by hand.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_sync():
            for vals in vals_list:
                vals.pop('is_auto', None)
        lines = super().create(vals_list)
        lines._check_editable({})
        return lines

    def write(self, vals):
        self._check_editable(vals)
        target = self.env['advanced.timesheet'].browse(vals.get('sheet_id'))
        if not self._is_sync() and target.state not in (False, 'draft'):
            raise UserError(_('Submitted timesheets cannot be changed. Reset it to draft first.'))
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        return super().unlink()

    def _grid_row_key(self):
        """Lines with the same key share a row on the grid."""
        self.ensure_one()
        return (self.project_id.id or 0, self.task_id.id or 0, int(self.is_auto))

    def _grid_auto_label(self):
        """Row title of automatic entries without a project."""
        return _('Automatic')

