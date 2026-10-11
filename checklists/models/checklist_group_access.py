# -*- coding: utf-8 -*-
"""Per-Checklist-Group permissions.

Every Checklist Group gets one security group per permission below, each
under its own privilege (they are independent, so each is its own dropdown
on the user's Access Rights), with the record rules that give it its
meaning. They are created, renamed and removed with the Checklist Group.

Users (Checklists / User) keep full use of checklists whose template has no
Checklist Group. For templates in a group, what they can do comes from that
group's permissions; Administrators can do everything.
"""
from odoo import api, fields, models

# Own checklists: the ones the user created or completed.
OWN = "'|', ('{p}create_uid', '=', user.id), ('{p}user_id', '=', user.id)"
IN_GROUP = "('{p}group_ids', 'in', [{gid}])"

# code -> (name, description, [(model, path to the record carrying the groups,
#          domain ('&' = in the group and own), perms from 'rwcu')]).
PERMISSIONS = {
    'template_author': (
        'Template Authoring',
        'Create and edit the templates in this Checklist Group, with their questions and button values.',
        [('checklist.template', '', IN_GROUP, 'wc'),
         ('checklist.question', 'template_id.', IN_GROUP, 'wcu'),
         ('checklist.question.option', 'question_id.template_id.', IN_GROUP, 'wcu'),
         ('checklist.question.condition', 'question_id.template_id.', IN_GROUP, 'wcu')],
    ),
    'template_delete': (
        'Template Delete',
        'Delete the templates in this Checklist Group.',
        [('checklist.template', '', IN_GROUP, 'u')],
    ),
    'record_own': (
        'Record Create and Edit Own',
        'Create checklists from the templates in this Checklist Group, and view and edit '
        'the ones they created or completed.',
        [('checklist.checklist', '', '&', 'rwc'),
         ('checklist.line', 'checklist_id.', '&', 'rwcu')],
    ),
    'record_all': (
        'Record Create and Edit All',
        'Create, view and edit every checklist from the templates in this Checklist Group.',
        [('checklist.checklist', '', IN_GROUP, 'rwc'),
         ('checklist.line', 'checklist_id.', IN_GROUP, 'rwcu')],
    ),
    'record_view': (
        'Record View All',
        'View every checklist from the templates in this Checklist Group.',
        [('checklist.checklist', '', IN_GROUP, 'r'),
         ('checklist.line', 'checklist_id.', IN_GROUP, 'r')],
    ),
    'delete_own': (
        'Record Delete Own',
        'Delete the checklists from the templates in this Checklist Group that they created or completed.',
        [('checklist.checklist', '', '&', 'ru'),
         ('checklist.line', 'checklist_id.', '&', 'r')],
    ),
    'delete_all': (
        'Record Delete All',
        'Delete every checklist from the templates in this Checklist Group.',
        [('checklist.checklist', '', IN_GROUP, 'ru'),
         ('checklist.line', 'checklist_id.', IN_GROUP, 'r')],
    ),
}
TEMPLATE_PERMISSIONS = ('template_author', 'template_delete')
CREATE_PERMISSIONS = ('record_own', 'record_all')
PERM_FIELDS = {'r': 'perm_read', 'w': 'perm_write', 'c': 'perm_create', 'u': 'perm_unlink'}


def _rule_domain(domain, path, gid):
    if domain == '&':  # in the group and own
        return "['&', %s, %s]" % (IN_GROUP.format(p=path, gid=gid), OWN.format(p=path))
    return '[%s]' % domain.format(p=path, gid=gid)


class ChecklistGroupAccess(models.Model):
    _name = 'checklist.group.access'
    _description = 'Checklist Group Permission'
    _order = 'checklist_group_id, sequence'

    checklist_group_id = fields.Many2one(
        'checklist.group', string='Checklist Group', required=True, ondelete='cascade', index=True,
    )
    code = fields.Selection(
        [(code, name) for code, (name, _desc, _rules) in PERMISSIONS.items()],
        string='Permission', required=True,
    )
    sequence = fields.Integer()
    privilege_id = fields.Many2one('res.groups.privilege', string='Privilege', ondelete='set null')
    res_group_id = fields.Many2one('res.groups', string='Security Group', ondelete='set null')
    rule_ids = fields.Many2many('ir.rule', string='Record Rules')

    _code_uniq = models.Constraint(
        'UNIQUE (checklist_group_id, code)', 'A Checklist Group has each permission once.',
    )

    def _name_for(self, group_name):
        self.ensure_one()
        return '%s: %s' % (group_name, PERMISSIONS[self.code][0])

    @api.model
    def _sync_for_groups(self, checklist_groups):
        """Create (or rename) the permissions of these Checklist Groups."""
        checklist_groups = checklist_groups.with_context(active_test=False)
        category = self.env.ref('checklists.module_category_checklists')
        user_group = self.env.ref('checklists.group_checklist_user')
        author_group = self.env.ref('checklists.group_checklist_template_author')
        for checklist_group in checklist_groups:
            existing = {access.code: access for access in checklist_group.sudo().access_ids}
            for sequence, (code, (name, description, rules)) in enumerate(PERMISSIONS.items()):
                access = existing.get(code) or self.sudo().create({
                    'checklist_group_id': checklist_group.id, 'code': code, 'sequence': sequence,
                })
                label = access._name_for(checklist_group.name)
                if not access.privilege_id:
                    access.privilege_id = self.env['res.groups.privilege'].sudo().create({
                        'name': label, 'category_id': category.id,
                        'sequence': 100 + checklist_group.id * 10 + sequence,
                        'description': description,
                    })
                else:
                    access.privilege_id.name = label
                implied = author_group if code in TEMPLATE_PERMISSIONS else user_group
                if not access.res_group_id:
                    access.res_group_id = self.env['res.groups'].sudo().create({
                        'name': 'Allowed', 'privilege_id': access.privilege_id.id,
                        'comment': description, 'implied_ids': [(4, implied.id)],
                    })
                # Rules are created per model, so a model added to a permission
                # later gets its rule on the next upgrade.
                ruled = set(access.rule_ids.mapped('model_id.model'))
                new_rules = [r for r in rules if r[0] not in ruled]
                if new_rules:
                    access.rule_ids = [(4, rule.id) for rule in self.env['ir.rule'].sudo().create([{
                        'name': '%s (%s)' % (label, model),
                        'model_id': self.env['ir.model']._get_id(model),
                        'groups': [(4, access.res_group_id.id)],
                        'domain_force': _rule_domain(domain, path, checklist_group.id),
                        **{field: letter in perms for letter, field in PERM_FIELDS.items()},
                    } for model, path, domain, perms in new_rules])]
                for rule in access.rule_ids:
                    rule.name = '%s (%s)' % (label, rule.model_id.model)
        return True

    def _remove(self):
        """Delete these permissions with their privilege, security group and rules."""
        accesses = self.sudo()
        accesses.rule_ids.unlink()
        groups = accesses.res_group_id
        privileges = accesses.privilege_id
        accesses.unlink()
        groups.unlink()
        privileges.unlink()

    @api.model
    def _sync_all(self):
        """Run on install/upgrade: every Checklist Group gets its permissions."""
        self._sync_for_groups(self.env['checklist.group'].with_context(active_test=False).search([]))

    @api.model
    def _user_group_ids(self, codes):
        """Checklist Groups in which the current user has any of these permissions."""
        accesses = self.sudo().search([
            ('code', 'in', list(codes)), ('res_group_id', 'in', self.env.user.all_group_ids.ids),
        ])
        return accesses.checklist_group_id.ids
