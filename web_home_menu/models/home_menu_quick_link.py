from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ALLOWED_URL_PREFIXES = ('/', 'http://', 'https://', 'mailto:', 'tel:')


class HomeMenuQuickLink(models.Model):
    _name = 'home.menu.quick.link'
    _description = 'Home Screen Quick Launch Button'
    _order = 'sequence, id'

    name = fields.Char(string='Label', required=True, translate=True)
    url = fields.Char(
        string='URL',
        required=True,
        help='Where the button takes the user: a page in Odoo (e.g. /odoo/action-contacts) '
             'or a full web address (e.g. https://example.com).',
    )
    new_tab = fields.Boolean(string='Open in New Tab')
    image = fields.Image(
        string='Icon Image',
        max_width=128,
        max_height=128,
        help='Picture shown on the button. Leave empty to use the icon below.',
    )
    icon = fields.Char(
        string='Icon',
        default='fa-link',
        help='FontAwesome icon class shown when there is no icon image (e.g. fa-link, fa-globe).',
    )
    color = fields.Char(
        string='Colour',
        default='#714B67',
        help='Background colour behind the icon.',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    user_id = fields.Many2one(
        'res.users',
        string='User',
        ondelete='cascade',
        index=True,
        help='Leave empty to show this button to everyone. When set, only that user '
             'sees it, after the buttons shown to everyone.',
    )

    @api.constrains('url')
    def _check_url(self):
        for link in self:
            if not (link.url or '').strip().lower().startswith(ALLOWED_URL_PREFIXES):
                raise ValidationError(_(
                    'The URL of "%(name)s" must start with "/", "http://", "https://", '
                    '"mailto:" or "tel:".',
                    name=link.name,
                ))

    @api.model
    def get_quick_links(self):
        """Buttons for the current user's quick launch bar: the ones shown to
        everyone first, then the user's own."""
        is_admin = self.env.user.has_group('base.group_erp_manager')
        links = self.search([('user_id', '=', False)]) + self.search([('user_id', '=', self.env.uid)])
        return [{
            'id': link.id,
            'name': link.name,
            'url': link.url.strip(),
            'new_tab': link.new_tab,
            'icon': link.icon or 'fa-link',
            'color': link.color or '#714B67',
            'image_url': link.image and '/web/image/home.menu.quick.link/%s/image?unique=%s' % (
                link.id, fields.Datetime.to_string(link.write_date).replace(' ', '_')),
            'is_default': not link.user_id,
            'editable': is_admin or link.user_id.id == self.env.uid,
        } for link in links]
