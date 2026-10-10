# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .esm_fak_template import QUESTION_TYPES


class EsmEedInspection(models.Model):
    _name = 'esm.eed.inspection'
    _description = 'Emergency Egress Door Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'inspection_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True, default='New',
    )
    template_id = fields.Many2one(
        'esm.eed.template', string='Template', required=True, tracking=True,
        ondelete='restrict', default=lambda self: self._default_template(),
    )
    inspection_date = fields.Date(
        string='Inspection Date', required=True, default=fields.Date.context_today, tracking=True,
    )
    inspector_id = fields.Many2one(
        'res.users', string='Inspector', required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    # Technical workflow state, so a fixed selection.
    state = fields.Selection(
        [('draft', 'In Progress'), ('done', 'Completed')],
        string='Status', default='draft', required=True, tracking=True, copy=False,
    )
    line_ids = fields.One2many(
        'esm.eed.inspection.line', 'inspection_id', string='Checks', copy=True,
    )
    notes = fields.Html(string='Notes')

    @api.model
    def _default_template(self):
        template_id = self.env['ir.config_parameter'].sudo().get_param(
            'esm_measures.eed_default_template_id')
        template = self.env['esm.eed.template'].browse(int(template_id or 0)).exists()
        return template if template.active else self.env['esm.eed.template']

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('esm.eed.inspection') or 'New'
            if vals.get('template_id') and not vals.get('line_ids'):
                template = self.env['esm.eed.template'].browse(vals['template_id'])
                vals['line_ids'] = self._template_line_commands(template)
        return super().create(vals_list)

    @api.model
    def _template_line_commands(self, template):
        return [Command.create(question._inspection_line_vals()) for question in template.question_ids]

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
            raise UserError(self.env._('The template of a completed inspection cannot be changed.'))
        return super().write(vals)


class EsmEedInspectionLine(models.Model):
    _name = 'esm.eed.inspection.line'
    _inherit = ['esm.inspection.line.mixin']
    _description = 'Emergency Egress Door Inspection Check'
    _order = 'inspection_id, sequence, id'

    inspection_id = fields.Many2one(
        'esm.eed.inspection', string='Inspection', required=True, ondelete='cascade', index=True,
    )
    state = fields.Selection(related='inspection_id.state')
    # The question is copied onto the line so later template edits don't
    # change what past inspections asked.
    question_id = fields.Many2one('esm.eed.question', string='Template Question', ondelete='set null')
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
        'esm.eed.question.option', string='Answer', ondelete='restrict',
        domain="[('question_id', '=', question_id)]",
    )
