# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .checklist_template import QUESTION_TYPES


class Checklist(models.Model):
    _name = 'checklist.checklist'
    _description = 'Checklist'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'checklist_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True, default='New',
    )
    template_id = fields.Many2one(
        'checklist.template', string='Template', required=True, tracking=True,
        ondelete='restrict', default=lambda self: self._default_template(),
    )
    group_ids = fields.Many2many(related='template_id.group_ids', string='Checklist Groups')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, tracking=True,
        default=lambda self: self.env.company,
    )
    checklist_date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today, tracking=True,
    )
    date_due = fields.Date(string='Due Date', tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Completed By', required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    # Technical workflow state, so a fixed selection.
    state = fields.Selection(
        [('draft', 'In Progress'), ('done', 'Completed')],
        string='Status', default='draft', required=True, tracking=True, copy=False,
    )
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    line_ids = fields.One2many(
        'checklist.line', 'checklist_id', string='Checks', copy=True,
    )
    notes = fields.Html(string='Notes')

    @api.model
    def _default_template(self):
        template_id = self.env['ir.config_parameter'].sudo().get_param('checklists.default_template_id')
        template = self.env['checklist.template'].browse(int(template_id or 0)).exists()
        return template if template.active else self.env['checklist.template']

    @api.depends('date_due', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for checklist in self:
            checklist.is_overdue = bool(
                checklist.state == 'draft' and checklist.date_due and checklist.date_due < today
            )

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(self.env._('Unsupported search on Overdue.'))
        domain = [('state', '=', 'draft'), ('date_due', '<', fields.Date.context_today(self))]
        return domain if (operator == '=') == value else ['!', '&'] + domain

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('checklist.checklist') or 'New'
            if vals.get('template_id') and not vals.get('line_ids'):
                template = self.env['checklist.template'].browse(vals['template_id'])
                vals['line_ids'] = self._template_line_commands(template)
        return super().create(vals_list)

    @api.model
    def _template_line_commands(self, template):
        return [Command.create(question._checklist_line_vals()) for question in template.question_ids]

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.state == 'draft':
            self.line_ids = [Command.clear()] + self._template_line_commands(self.template_id)

    def action_complete(self):
        self.write({'state': 'done'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def write(self, vals):
        if 'template_id' in vals and any(rec.state == 'done' for rec in self):
            raise UserError(self.env._('The template of a completed checklist cannot be changed.'))
        return super().write(vals)


class ChecklistLine(models.Model):
    _name = 'checklist.line'
    _description = 'Checklist Check'
    _order = 'checklist_id, sequence, id'

    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist', required=True, ondelete='cascade', index=True,
    )
    state = fields.Selection(related='checklist_id.state')
    # The question is copied onto the line so later template edits don't
    # change what past checklists asked.
    question_id = fields.Many2one('checklist.question', string='Template Question', ondelete='set null')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Question', required=True)
    description = fields.Text(string='Description')
    question_type = fields.Selection(QUESTION_TYPES, string='Type', required=True, default='text')

    value_text = fields.Char(string='Text')
    value_text_area = fields.Text(string='Text Area')
    value_number = fields.Float(string='Number')
    value_integer = fields.Integer(string='Integer')
    value_date = fields.Date(string='Date')
    value_datetime = fields.Datetime(string='Datetime')
    value_option_id = fields.Many2one(
        'checklist.question.option', string='Answer', ondelete='restrict',
        domain="[('question_id', '=', question_id)]",
    )

    def _answer_display(self):
        """The answer as text, for reports (dates as dd/mm/yyyy)."""
        self.ensure_one()
        kind = self.question_type
        if kind == 'text':
            return self.value_text or ''
        if kind == 'text_area':
            return self.value_text_area or ''
        if kind == 'number':
            return ('%.2f' % self.value_number).rstrip('0').rstrip('.')
        if kind == 'integer':
            return str(self.value_integer)
        if kind == 'date':
            return self.value_date.strftime('%d/%m/%Y') if self.value_date else ''
        if kind == 'datetime':
            if not self.value_datetime:
                return ''
            return fields.Datetime.context_timestamp(self, self.value_datetime).strftime('%d/%m/%Y %H:%M')
        if kind == 'buttons':
            return self.value_option_id.name or ''
        return ''

    def _answer_badge_style(self):
        """Inline style colouring a Buttons answer like its button, or ''."""
        self.ensure_one()
        colour = self.question_type == 'buttons' and self.value_option_id.color
        if not colour:
            return ''
        hex_colour = colour.lstrip('#')
        try:
            r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return ''
        text = '#000' if 0.299 * r + 0.587 * g + 0.114 * b > 160 else '#fff'
        return f'background-color: {colour}; color: {text};'
