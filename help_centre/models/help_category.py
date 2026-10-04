from odoo import fields, models


class HelpCategory(models.Model):
    _name = 'help.category'
    _description = 'Help Centre Category'
    _order = 'sequence, name'
    _parent_name = 'parent_id'
    _parent_store = True

    name = fields.Char('Name', required=True, translate=True)
    description = fields.Text('Description', translate=True)
    icon = fields.Char('Icon', help="Font Awesome icon class, e.g. fa-book", default='fa-folder')
    color = fields.Integer('Colour Index', default=0)
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)

    parent_id = fields.Many2one(
        'help.category', 'Parent Category',
        ondelete='set null', index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('help.category', 'parent_id', 'Sub-categories')

    article_ids = fields.One2many('help.article', 'category_id', 'Articles')
    article_count = fields.Integer('Article Count', compute='_compute_article_count')

    def _compute_article_count(self):
        data = self.env['help.article'].read_group(
            [('category_id', 'in', self.ids), ('state', '=', 'published')],
            ['category_id'],
            ['category_id'],
        )
        counts = {d['category_id'][0]: d['category_id_count'] for d in data}
        for rec in self:
            rec.article_count = counts.get(rec.id, 0)
