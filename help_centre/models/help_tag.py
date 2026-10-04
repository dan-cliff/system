from odoo import fields, models


class HelpTag(models.Model):
    _name = 'help.tag'
    _description = 'Help Centre Tag'
    _order = 'name'

    name = fields.Char('Name', required=True, translate=True)
    color = fields.Integer('Colour Index', default=0)
    active = fields.Boolean('Active', default=True)
    article_count = fields.Integer('Articles', compute='_compute_article_count')

    def _compute_article_count(self):
        for tag in self:
            tag.article_count = self.env['help.article'].search_count(
                [('tag_ids', 'in', tag.id)]
            )
