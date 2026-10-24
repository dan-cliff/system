import base64
import logging

from odoo import models, tools
from odoo.tools.image import image_process

_logger = logging.getLogger(__name__)

# Home screen tiles are 64px: 128px keeps them sharp on high-DPI screens.
MENU_ICON_SIZE = 128


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @tools.ormcache('self.env.uid', 'debug', 'self.env.lang')
    def load_menus(self, debug):
        """Send app icons at tile size instead of as uploaded.

        The web client keeps the menus, icons included, in the browser's
        localStorage and shows that copy first on every full page load
        (refresh, or opening /odoo from another page). Full-size icons
        (1024px) make the menus several MB, too big for localStorage: the
        browser then can't save the new copy and keeps showing an old home
        screen until the user navigates to it from inside the web client.
        """
        menus = super().load_menus(debug)
        # The parent's result is cached and shared: never change it in place.
        result = dict(menus)
        for key, menu in menus.items():
            if key != 'root' and menu.get('web_icon_data'):
                result[key] = dict(menu, **self._home_menu_small_icon(
                    menu['web_icon_data'], menu['web_icon_data_mimetype']))
        return result

    def _home_menu_small_icon(self, data, mimetype):
        if mimetype not in ('image/png', 'image/jpeg', 'image/webp'):
            return {}  # SVGs are already small, and image_process can't resize them
        try:
            image = image_process(
                base64.b64decode(data), size=(MENU_ICON_SIZE, MENU_ICON_SIZE), output_format='PNG')
        except Exception:  # noqa: BLE001 - a bad icon must never break the menus
            _logger.warning("Could not resize a menu icon", exc_info=True)
            return {}
        return {'web_icon_data': base64.b64encode(image).decode(), 'web_icon_data_mimetype': 'image/png'}
