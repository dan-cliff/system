from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .org_config import DEFAULT_LABELS
from .org_scope_mixin import ORG_LEVELS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Settings › Organisational Management (stored by org.config).
    org_division_enabled = fields.Boolean(string='Use Divisions')
    org_division_label = fields.Char(string='Division label')
    org_division_plural = fields.Char(string='Division plural label')

    org_business_unit_enabled = fields.Boolean(string='Use Business Units')
    org_business_unit_label = fields.Char(string='Business Unit label')
    org_business_unit_plural = fields.Char(string='Business Unit plural label')
    # Technical choice of level (code depends on it), so a fixed selection.
    org_business_unit_parent = fields.Selection(
        [('division', 'Division')], string='Business Unit sits under')

    org_location_enabled = fields.Boolean(string='Use Locations')
    org_location_label = fields.Char(string='Location label')
    org_location_plural = fields.Char(string='Location plural label')
    org_location_parent = fields.Selection(
        [('division', 'Division'), ('business_unit', 'Business Unit')],
        string='Location sits under')

    org_department_enabled = fields.Boolean(string='Use Departments')
    org_department_label = fields.Char(string='Department label')
    org_department_plural = fields.Char(string='Department plural label')
    org_department_parent = fields.Selection(
        [('division', 'Division'), ('business_unit', 'Business Unit'), ('location', 'Location')],
        string='Department sits under')

    @api.model
    def get_values(self):
        res = super().get_values()
        config = self.env['org.config']._get_config()
        for level in ORG_LEVELS:
            res[f'org_{level}_enabled'] = config[level]['enabled']
            res[f'org_{level}_label'] = config[level]['label']
            res[f'org_{level}_plural'] = config[level]['plural']
            if f'org_{level}_parent' in self._fields:
                res[f'org_{level}_parent'] = config[level]['parent']
        return res

    def set_values(self):
        super().set_values()
        values = {}
        for level in ORG_LEVELS:
            singular, plural = DEFAULT_LABELS[level]
            values[level] = {
                'enabled': self[f'org_{level}_enabled'],
                'label': (self[f'org_{level}_label'] or '').strip() or singular,
                'plural': (self[f'org_{level}_plural'] or '').strip() or plural,
            }
            if f'org_{level}_parent' in self._fields:
                values[level]['parent'] = self[f'org_{level}_parent'] or ORG_LEVELS[ORG_LEVELS.index(level) - 1]
        if not any(level_values['enabled'] for level_values in values.values()):
            raise ValidationError(self.env._("Keep at least one organisation level enabled."))
        config = self.env['org.config']
        if values != {level: {k: v for k, v in config._get_config()[level].items() if k in values[level]}
                      for level in ORG_LEVELS}:
            config._set_config(values)
