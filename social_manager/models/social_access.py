"""Per Platform and per Page / Channel permissions.

Every Platform and every Page / Channel gets one privilege per permission
level, each holding a single group, so the levels show as separate choices
on the user form (a user can be e.g. both an Approver and a Moderator):

    Facebook / Approve Posts
    Facebook - Cliff's Country Crafts / Moderate Posts

A level granted on a Platform covers every Page / Channel of that Platform.
Every group implies Social Manager / User (app access), and "Create and Edit
Published" implies "Create and Edit Draft" of the same Platform / Page.
When Permission Management is installed a role is created for each level too.
"""
from odoo import api, fields, models

LEVELS = [
    ('draft', 'Create and Edit Draft',
     'Can create and edit draft posts and submit them for approval, but not publish them.'),
    ('publish', 'Create and Edit Published',
     'Can create, edit, schedule and publish posts, and edit published posts.'),
    ('approve', 'Approve Posts', 'Can approve or reject posts submitted for approval.'),
    ('moderate', 'Moderate Posts',
     'Can reply to, hide and delete comments, and review comments flagged for moderation.'),
    ('delete', 'Delete Posts', 'Can delete posts, in Odoo and on the platform.'),
]
LEVEL_KEYS = [key for key, _label, _comment in LEVELS]
LEVEL_LABELS = {key: label for key, label, _comment in LEVELS}
ROLE_PREFIX = 'Social Manager: '


class SocialAccessMixin(models.AbstractModel):
    _name = 'social.access.mixin'
    _description = 'Social Manager Permission Levels'

    group_draft_id = fields.Many2one('res.groups', string='Create and Edit Draft Group',
                                     readonly=True, copy=False, ondelete='set null')
    group_publish_id = fields.Many2one('res.groups', string='Create and Edit Published Group',
                                       readonly=True, copy=False, ondelete='set null')
    group_approve_id = fields.Many2one('res.groups', string='Approve Posts Group',
                                       readonly=True, copy=False, ondelete='set null')
    group_moderate_id = fields.Many2one('res.groups', string='Moderate Posts Group',
                                        readonly=True, copy=False, ondelete='set null')
    group_delete_id = fields.Many2one('res.groups', string='Delete Posts Group',
                                      readonly=True, copy=False, ondelete='set null')

    # ------------------------------------------------------------------
    # Hooks for the concrete models
    # ------------------------------------------------------------------
    def _social_access_label(self):
        """Name shown for this record's privileges, e.g. "Facebook" or "Facebook - My Page"."""
        self.ensure_one()
        return self.display_name

    def _social_access_sequence(self):
        return 100

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._social_access_sync()
        return records

    def write(self, vals):
        result = super().write(vals)
        if self._social_access_rename_fields() & set(vals):
            self._social_access_sync()
        return result

    def _social_access_rename_fields(self):
        return {'name'}

    def unlink(self):
        self._social_access_remove()
        return super().unlink()

    def _social_access_groups(self):
        """All permission groups of these records."""
        groups = self.env['res.groups']
        for key in LEVEL_KEYS:
            groups |= self.mapped('group_%s_id' % key)
        return groups

    def _social_access_sync(self):
        """Create the privileges/groups (and roles) that are missing and keep their names current."""
        Groups = self.env['res.groups'].sudo()
        Privilege = self.env['res.groups.privilege'].sudo()
        category = self.env.ref('social_manager.module_category_social_manager_access')
        user_group = self.env.ref('social_manager.group_social_user')
        for record in self.sudo():
            label = record._social_access_label()
            vals = {}
            for index, (key, level_label, comment) in enumerate(LEVELS):
                privilege_name = '%s / %s' % (label, level_label)
                group = record['group_%s_id' % key]
                if group:
                    if group.privilege_id.name != privilege_name:
                        group.privilege_id.name = privilege_name
                    continue
                privilege = Privilege.create({
                    'name': privilege_name,
                    'category_id': category.id,
                    'sequence': record._social_access_sequence() * 10 + index,
                    'description': comment,
                })
                implied = user_group
                if key == 'publish' and record.group_draft_id:
                    implied |= record.group_draft_id
                group = Groups.create({
                    'name': level_label,
                    'privilege_id': privilege.id,
                    'comment': comment,
                    'implied_ids': [(6, 0, implied.ids)],
                })
                vals['group_%s_id' % key] = group.id
                if key == 'draft':
                    # So "publish", created after it in this loop, can imply it.
                    record.group_draft_id = group
            if vals:
                super(SocialAccessMixin, record).write(vals)
        self._social_access_sync_roles()

    def _social_access_sync_roles(self):
        """One Permission Management role per level (when that app is installed)."""
        if 'permission.role' not in self.env:
            return
        Role = self.env['permission.role'].sudo()
        RoleLine = self.env['permission.role.line'].sudo()
        for record in self.sudo():
            label = record._social_access_label()
            for key, level_label, comment in LEVELS:
                group = record['group_%s_id' % key]
                if not group:
                    continue
                name = '%s%s - %s' % (ROLE_PREFIX, label, level_label)
                line = RoleLine.search([('group_id', '=', group.id)], limit=1)
                if line:
                    if line.role_id.name != name:
                        line.role_id.name = name
                    continue
                Role.create({
                    'name': name,
                    'description': '%s (%s)' % (comment, label),
                    'line_ids': [(0, 0, {'privilege_id': group.privilege_id.id, 'group_id': group.id})],
                })

    def _social_access_remove(self):
        groups = self._social_access_groups().sudo()
        if not groups:
            return
        if 'permission.role.line' in self.env:
            lines = self.env['permission.role.line'].sudo().search([('group_id', 'in', groups.ids)])
            roles = lines.role_id
            lines.unlink()
            roles.filtered(lambda role: not role.line_ids).unlink()
        privileges = groups.privilege_id
        groups.unlink()
        privileges.filtered(lambda privilege: not privilege.group_ids).unlink()

    @api.model
    def _social_access_sync_all(self):
        """Called on every install/upgrade: create missing permissions and roles."""
        self.env['social.platform'].with_context(active_test=False).search([])._social_access_sync()
        self.env['social.channel'].with_context(active_test=False).search([])._social_access_sync()
