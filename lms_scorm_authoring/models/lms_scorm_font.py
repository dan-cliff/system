from odoo import api, fields, models


class LmsScormFont(models.Model):
    _name = 'lms.scorm.font'
    _description = 'SCORM Course Font'
    _order = 'sequence, name'

    name = fields.Char(string='Font', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    css_family = fields.Char(
        string='CSS Font Stack', required=True,
        help="What the course uses as its CSS font-family, e.g. 'Open Sans', Arial, sans-serif.",
    )
    google_font = fields.Char(
        string='Google Font Name',
        help='Family name to load from Google Fonts (e.g. Open Sans). Leave empty for fonts '
             'every device already has, such as Arial or Georgia.',
    )

    @api.model
    def _match_company_font(self, company_font):
        """Font matching a res.company report font value (e.g. 'Open_Sans')."""
        if not company_font:
            return self.browse()
        name = company_font.replace('_', ' ')
        return self.search(['|', ('name', '=ilike', name), ('google_font', '=ilike', name)], limit=1)

    def _google_font_url(self):
        self.ensure_one()
        if not self.google_font:
            return ''
        return 'https://fonts.googleapis.com/css2?family=%s:ital,wght@0,400;0,700;1,400&display=swap' % (
            self.google_font.strip().replace(' ', '+'))
