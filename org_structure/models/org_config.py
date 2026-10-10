import re

from odoo import api, models, tools
from odoo.tools import frozendict

from .org_scope_mixin import ORG_LEVELS

DEFAULT_LABELS = {
    'division': ('Division', 'Divisions'),
    'business_unit': ('Business Unit', 'Business Units'),
    'location': ('Location', 'Locations'),
    'department': ('Department', 'Departments'),
}
PARAM = 'org_structure.%s_%s'


class OrgConfig(models.AbstractModel):
    """Settings › Organisational Management, stored as system parameters.

    Per level: whether it is enabled, its label (singular and plural) and
    which higher level it hangs under. A disabled level is hidden
    everywhere and levels below it hang under the next enabled level up.
    """
    _name = 'org.config'
    _description = 'Organisation Configuration'

    @api.model
    @tools.ormcache()
    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        config = {}
        for index, level in enumerate(ORG_LEVELS):
            singular, plural = DEFAULT_LABELS[level]
            default_parent = ORG_LEVELS[index - 1] if index else False
            parent = ICP.get_param(PARAM % (level, 'parent')) or default_parent
            if parent not in ORG_LEVELS[:index]:
                parent = default_parent
            config[level] = {
                'enabled': ICP.get_param(PARAM % (level, 'enabled'), 'True') == 'True',
                'label': ICP.get_param(PARAM % (level, 'label')) or singular,
                'plural': ICP.get_param(PARAM % (level, 'plural')) or plural,
                'parent': parent,
            }
        for level in ORG_LEVELS:
            # The parent actually used: skip disabled levels on the way up.
            parent = config[level]['parent']
            while parent and not config[parent]['enabled']:
                index = ORG_LEVELS.index(parent)
                parent = ORG_LEVELS[index - 1] if index else False
            config[level]['effective_parent'] = parent
        return frozendict({level: frozendict(values) for level, values in config.items()})

    @api.model
    def _set_config(self, values):
        """``values``: {level: {'enabled', 'label', 'plural', 'parent'}}."""
        ICP = self.env['ir.config_parameter'].sudo()
        for level, level_values in values.items():
            for key, value in level_values.items():
                if key == 'enabled':
                    value = 'True' if value else 'False'
                ICP.set_param(PARAM % (level, key), value or False)
        self._clear_caches()
        self._apply_labels()

    @api.model
    def _clear_caches(self):
        # Field labels, views and record rules all depend on the config.
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    @api.model
    def _is_enabled(self, level):
        return self._get_config()[level]['enabled']

    @api.model
    def _parent_level(self, level):
        return self._get_config()[level]['effective_parent']

    @api.model
    def _label(self, level, plural=False):
        return self._get_config()[level]['plural' if plural else 'label']

    # ------------------------------------------------------------------
    # Relabelling: the field code stays the same, only what users read
    # ------------------------------------------------------------------

    @api.model
    @tools.ormcache()
    def _relabel_rules(self):
        config = self._get_config()
        rules = []
        for level in ORG_LEVELS:
            singular, plural = DEFAULT_LABELS[level]
            new_singular, new_plural = config[level]['label'], config[level]['plural']
            # plural first, so "Business Units" isn't turned into "<label>s"
            for old, new in ((plural, new_plural), (singular, new_singular)):
                if old != new:
                    rules.append((old, new))
                    rules.append((old.lower(), new.lower()))
        if not rules:
            return None
        pattern = re.compile(r'\b(%s)\b' % '|'.join(re.escape(old) for old, _new in rules))
        return pattern, dict(rules)

    @api.model
    def _relabel(self, text):
        if not text or not isinstance(text, str):
            return text
        rules = self._relabel_rules()
        if not rules:
            return text
        pattern, mapping = rules
        return pattern.sub(lambda match: mapping[match.group(0)], text)

    @api.model
    def _post_update(self):
        """Install/upgrade step (data/org_config_data.xml)."""
        # Old Settings › Organisation menus: children first, otherwise
        # deleting the parent would promote them to home-screen apps.
        for xmlid in ('menu_org_division', 'menu_org_business_unit', 'menu_org_location',
                      'menu_org_department', 'menu_org_structure', 'menu_org_structure_settings',
                      'menu_org_structure_root'):
            menu = self.env.ref(f'org_structure.{xmlid}', raise_if_not_found=False)
            if menu:
                menu.sudo().unlink()
        self._apply_labels()

    @api.model
    def _apply_labels(self):
        """Window action names and help follow the labels (they are records,
        not views, so they are rewritten rather than relabelled on the fly)."""
        for level in ORG_LEVELS:
            action = self.env.ref(f'org_structure.action_org_{level}', raise_if_not_found=False)
            if not action:
                continue
            singular = self._label(level)
            action.sudo().write({
                'name': self._label(level, plural=True),
                'help': f'<p class="o_view_nocontent_smiling_face">Create your first {singular.lower()}</p>',
            })
