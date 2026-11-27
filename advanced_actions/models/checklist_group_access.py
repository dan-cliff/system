from odoo import api, models
from odoo.addons.checklists.models.checklist_group_access import IN_GROUP, PERM_FIELDS, _rule_domain

# Actions raised from a checklist follow the checklist's Checklist Group
# permissions, like its checks: permission code -> (domain, perms).
ACTION_RULES = {
    'record_own': ('&', 'rwcu'),
    'record_all': (IN_GROUP, 'rwcu'),
    'record_view': (IN_GROUP, 'r'),
    'delete_own': ('&', 'r'),
    'delete_all': (IN_GROUP, 'r'),
}


class ChecklistGroupAccess(models.Model):
    _inherit = 'checklist.group.access'

    @api.model
    def _sync_for_groups(self, checklist_groups):
        res = super()._sync_for_groups(checklist_groups)
        model_id = self.env['ir.model']._get_id('advanced.action')
        accesses = self.sudo().search([
            ('checklist_group_id', 'in', checklist_groups.ids), ('code', 'in', list(ACTION_RULES)),
        ])
        for access in accesses:
            label = access._name_for(access.checklist_group_id.name)
            rule = access.rule_ids.filtered(lambda r: r.model_id.id == model_id)
            if rule:
                rule.name = '%s (advanced.action)' % label
                continue
            domain, perms = ACTION_RULES[access.code]
            access.rule_ids = [(0, 0, {
                'name': '%s (advanced.action)' % label,
                'model_id': model_id,
                'groups': [(4, access.res_group_id.id)],
                'domain_force': _rule_domain(domain, 'source_checklist_id.', access.checklist_group_id.id),
                **{field: letter in perms for letter, field in PERM_FIELDS.items()},
            })]
        return res
