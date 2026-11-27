# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


INLINE_TAGS = re.compile(r'</?(strong|b|em|i|u|span)(\s[^>]*)?>', re.I)


HEADINGS = re.compile(r'<(/?)h[1-6](\s[^>]*)?>', re.I)
LIST_ITEM = re.compile(r'<li(\s[^>]*)?>', re.I)


def plain_text(html):
    """The text of formatted content: headings and paragraphs on their own lines,
    list items as "• " lines, and no *asterisks* for bold, italics or headings."""
    html = INLINE_TAGS.sub('', html or '')
    html = HEADINGS.sub(lambda m: '<%sp>' % m.group(1), html)
    html = LIST_ITEM.sub('<p>• ', html)
    html = re.sub(r'</li>', '</p>', html, flags=re.I)
    html = re.sub(r'</?(ul|ol)(\s[^>]*)?>', '', html, flags=re.I)
    text = html2plaintext(html)
    return '\n'.join(line.rstrip() for line in text.splitlines()).strip()


class TextBlockCategory(models.Model):
    """Groups text blocks (e.g. Care Instructions, Materials, Shipping)."""
    _name = 'text.block.category'
    _description = 'Text Block Category'
    _order = 'sequence, name, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class TextBlock(models.Model):
    """A reusable piece of formatted text, inserted into rich text fields such as a
    product's eCommerce Description or Quotation Description."""
    _name = 'text.block'
    _description = 'Text Block'
    _order = 'sequence, name, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category_id = fields.Many2one('text.block.category', string='Category', ondelete='restrict')
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        help='Only offered for this company. Leave empty to share it with every company.')
    content = fields.Html(string='Content', required=True, translate=True)
    preview = fields.Char(string='Preview', compute='_compute_preview')

    @api.depends('content')
    def _compute_preview(self):
        for block in self:
            text = ' '.join(plain_text(block.content).split())
            block.preview = text[:120] + ('…' if len(text) > 120 else '')

    @api.model
    def text_block_list(self, company_id=False):
        """The blocks the picker offers: shared ones and the company's own."""
        company = self.env['res.company'].browse(company_id).exists() if company_id else self.env.company
        blocks = self.search(['|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return [{
            'id': block.id,
            'name': block.name,
            'category': block.category_id.name or '',
            'category_id': block.category_id.id or False,
            'content': block.content or '',
            'preview': block.preview,
        } for block in blocks]

    def text_block_value(self, as_text=False):
        """The block to insert: its HTML, or plain text for a plain text field."""
        self.ensure_one()
        if not self.exists():
            raise UserError(self.env._('This text block no longer exists.'))
        if as_text:
            return plain_text(self.content)
        return self.content or ''
