# -*- coding: utf-8 -*-
from odoo import Command, fields, models
from odoo.exceptions import UserError


class TalentSeekLocationWizard(models.TransientModel):
    _name = 'talent.seek.location.wizard'
    _description = 'Find a SEEK Location'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True, ondelete='cascade')
    query = fields.Char(string='Suburb, town or city')
    result_ids = fields.Many2many('talent.seek.location', string='Found on SEEK')
    location_id = fields.Many2one('talent.seek.location', string='Location', domain="[('id', 'in', result_ids)]")

    def action_search(self):
        self.ensure_one()
        if not self.query or len(self.query.strip()) < 2:
            raise UserError(self.env._('Type at least two letters of the place.'))
        found = self.env['talent.seek.location']._seek_lookup(self.query.strip())
        self.write({'result_ids': [Command.set(found.ids)], 'location_id': found[:1].id})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Find a SEEK Location'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        self.ensure_one()
        if not self.location_id:
            raise UserError(self.env._('Search, then pick a location.'))
        self.job_id.seek_location_id = self.location_id
        return {'type': 'ir.actions.act_window_close'}
