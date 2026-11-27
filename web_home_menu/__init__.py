from . import models

# Odoo's own icons for the menus we restyle in data/menu_icons.xml.
_BASE_MENU_ICONS = {
    'base.menu_management': 'base,static/description/modules.png',
    'base.menu_administration': 'base,static/description/settings.png',
}


def uninstall_hook(env):
    """Give the Apps and Settings menus Odoo's icons back."""
    for xmlid, icon in _BASE_MENU_ICONS.items():
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.web_icon = icon
