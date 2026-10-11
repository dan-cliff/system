# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChecklistGroup(models.Model):
    _name = 'checklist.group'
    _description = 'Checklist Group'
    _order = 'sequence, name'

    name = fields.Char(string='Group Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')
    template_ids = fields.Many2many(
        'checklist.template', 'checklist_template_group_rel', 'group_id', 'template_id',
        string='Templates',
    )
    template_count = fields.Integer(compute='_compute_template_count', string='# Templates')
    # The group's permissions (see checklist_group_access.py).
    access_ids = fields.One2many('checklist.group.access', 'checklist_group_id', string='Permissions')

    _name_uniq = models.Constraint('UNIQUE (name)', 'A Checklist Group with this name already exists.')

    @api.depends('template_ids')
    def _compute_template_count(self):
        for group in self:
            group.template_count = len(group.template_ids)

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        self.env['checklist.group.access']._sync_for_groups(groups)
        return groups

    def write(self, vals):
        result = super().write(vals)
        if 'name' in vals:
            self.env['checklist.group.access']._sync_for_groups(self)
        return result

    def unlink(self):
        self.sudo().access_ids._remove()
        return super().unlink()
