from markupsafe import Markup

from odoo import _, api, fields, models

from ..models.advanced_project_collaborator import ACCESS_MANAGER_GROUP, COLLABORATOR_TYPES


class AdvancedProjectInvite(models.TransientModel):
    """Invite people onto a project's team as Colleagues or Customers.

    Colleagues keep their permissions. Customers need the Project Customer
    permission set (a portal login plus the Project Customer group); when they
    don't have it the wizard flags it and, for people allowed to manage
    customer access, offers to update it."""
    _name = 'advanced.project.invite'
    _description = 'Invite to Project'

    project_id = fields.Many2one('advanced.project', string='Project', required=True, ondelete='cascade')
    collaborator_type = fields.Selection(
        COLLABORATOR_TYPES, string='Invite As', required=True, default='colleague',
        help='Colleague: added to the team with their permissions left as they are. Customer: sees only '
             'the projects they are a Customer on, through the customer portal.')
    partner_ids = fields.Many2many(
        'res.partner', 'advanced_project_invite_partner_rel', 'invite_id', 'partner_id',
        string='People', required=True)
    send_invitation = fields.Boolean('Send Invitation Email', default=True)
    message = fields.Text('Message', help='Added to the invitation email.')
    access_warning = fields.Html(compute='_compute_access', sanitize=False)
    has_issues = fields.Boolean(compute='_compute_access')
    fixable_count = fields.Integer(compute='_compute_access')
    can_fix_access = fields.Boolean(compute='_compute_access')
    update_permissions = fields.Boolean(
        'Update Their Permissions', default=True,
        help='Give these customers the Project Customer permission set: a portal login (an invitation '
             'email is sent to set a password) and access to the projects they are a Customer on.')

    @api.depends('partner_ids', 'collaborator_type', 'project_id')
    def _compute_access(self):
        Collaborator = self.env['advanced.project.collaborator']
        can_fix = self.env.user.has_group(ACCESS_MANAGER_GROUP)
        for wizard in self:
            issues = []
            fixable = 0
            on_team = wizard.project_id.collaborator_ids
            for partner in wizard.partner_ids:
                partner = partner._origin or partner
                state, message = Collaborator.sudo()._access_check_for(
                    partner, wizard.collaborator_type, wizard.project_id._origin or wizard.project_id)
                if state != 'ok':
                    issues.append((state, message))
                    fixable += state in ('no_user', 'no_group')
                existing = on_team.filtered(lambda c: c.partner_id == partner)
                if existing and existing.collaborator_type != wizard.collaborator_type:
                    issues.append(('info', _('%(name)s is already on the team as a %(type)s, and will be '
                                             'changed to a %(new)s.', name=partner.display_name,
                                             type=dict(COLLABORATOR_TYPES)[existing.collaborator_type],
                                             new=dict(COLLABORATOR_TYPES)[wizard.collaborator_type])))
            wizard.has_issues = any(state != 'info' for state, __ in issues)
            wizard.fixable_count = fixable if wizard.collaborator_type == 'customer' else 0
            wizard.can_fix_access = can_fix
            wizard.access_warning = Markup('').join(
                Markup('<li>%s</li>') % message for __, message in issues
            ) if issues else False
            if issues:
                wizard.access_warning = Markup('<ul class="mb-0">%s</ul>') % wizard.access_warning

    def action_invite(self):
        self.ensure_one()
        project = self.project_id
        Collaborator = self.env['advanced.project.collaborator']
        collaborators = Collaborator
        for partner in self.partner_ids:
            existing = project.collaborator_ids.filtered(lambda c: c.partner_id == partner)
            if existing:
                if existing.collaborator_type != self.collaborator_type:
                    existing.collaborator_type = self.collaborator_type
                collaborators |= existing
            else:
                collaborators |= Collaborator.create({
                    'project_id': project.id, 'partner_id': partner.id,
                    'collaborator_type': self.collaborator_type,
                })
        if (self.collaborator_type == 'customer' and self.update_permissions and self.can_fix_access):
            collaborators.filtered(lambda c: c.access_state in ('no_user', 'no_group')).action_fix_access()
        if self.send_invitation:
            collaborators.action_send_invitation(self.message)
        type_label = dict(COLLABORATOR_TYPES)[self.collaborator_type]
        project._message_log(body=Markup('<p>%s</p>') % _(
            'Invited %(people)s as %(type)s.', people=', '.join(collaborators.partner_id.mapped('display_name')),
            type=type_label))

        collaborators.invalidate_recordset(['user_id', 'access_state', 'access_message'])
        remaining = collaborators.filtered(lambda c: c.access_state != 'ok')
        if not remaining:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Invited, but some people cannot open the project yet'),
                'message': '\n'.join(remaining.mapped('access_message')),
                'type': 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
