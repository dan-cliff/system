# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .seek_api import SEEK_SCHEME

CATEGORIES_QUERY = """
query TalentSeekCategories($schemeId: String!) {
  jobCategories(schemeId: $schemeId) {
    id { value }
    name
    children { id { value } name }
  }
}
"""


class TalentSeekCategory(models.Model):
    _name = 'talent.seek.category'
    _description = 'SEEK Job Category'
    _order = 'complete_name'
    _rec_name = 'complete_name'
    _parent_store = True

    name = fields.Char(required=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True)
    seek_id = fields.Char(string='SEEK ID', required=True, index=True)
    parent_id = fields.Many2one('talent.seek.category', string='Parent Category', ondelete='cascade', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('talent.seek.category', 'parent_id', string='Sub-categories')
    active = fields.Boolean(default=True)

    _seek_id_uniq = models.Constraint('UNIQUE (seek_id)', 'This SEEK category is already listed.')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            category.complete_name = ('%s › %s' % (category.parent_id.complete_name, category.name)
                                      if category.parent_id else category.name)

    @api.model
    def _seek_sync(self, company=None):
        """Load SEEK's job categories (SEEK ads are posted against a sub-category)."""
        data = self.env['talent.seek.api']._seek_query(CATEGORIES_QUERY, {'schemeId': SEEK_SCHEME}, company)
        Categories = self.with_context(active_test=False).sudo()
        seen = Categories.browse()
        for parent_data in data.get('jobCategories') or []:
            parent = Categories._seek_upsert(parent_data, False)
            seen |= parent
            for child_data in parent_data.get('children') or []:
                seen |= Categories._seek_upsert(child_data, parent.id)
        (Categories.search([]) - seen).write({'active': False})
        return len(seen)

    def _seek_upsert(self, data, parent_id):
        vals = {'name': data['name'], 'parent_id': parent_id, 'active': True}
        category = self.search([('seek_id', '=', data['id']['value'])], limit=1)
        if category:
            category.write(vals)
            return category
        return self.create(dict(vals, seek_id=data['id']['value']))
