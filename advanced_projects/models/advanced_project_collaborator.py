from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Customer or Colleague: the record rules and the invitation depend on it,
# so it stays a fixed selection (CLAUDE.md > Choice fields: technical states).
COLLABORATOR_TYPES = [
    ('colleague', 'Colleague'),
    ('customer', 'Customer'),
]

ACCESS_STATES = [
    ('ok', 'Has Access'),
    ('no_user', 'No Portal Login'),
    ('no_group', 'Missing Customer Permission'),
    ('internal_user', 'Employee User'),
    ('not_employee', 'Not an Employee User'),
    ('no_permission', 'No Project Permission'),
]

CUSTOMER_GROUP = 'advanced_projects.group_advanced_project_customer'
ACCESS_MANAGER_GROUP = 'advanced_projects.group_advanced_project_customer_access'


class AdvancedProjectCollaborator(models.Model):
    _name = 'advanced.project.collaborator'
    _description = 'Project Team Member'
    _order = 'collaborator_type, id'
    _rec_name = 'partner_id'

    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Person', required=True, index=True, ondelete='cascade')
    email = fields.Char(related='partner_id.email')
    collaborator_type = fields.Selection(
        COLLABORATOR_TYPES, string='Type', required=True, default='colleague',
        help='Colleague: an employee working on the project; their permissions are left as they are. '
             'Customer: sees only the projects they are a Customer on, through the customer portal.')
    user_id = fields.Many2one('res.users', string='User', compute='_compute_user_id', compute_sudo=True)
    access_state = fields.Selection(
        ACCESS_STATES, string='Access', compute='_compute_access_state', compute_sudo=True)
    access_message = fields.Char('Access Notes', compute='_compute_access_state', compute_sudo=True)
    can_fix_access = fields.Boolean(compute='_compute_access_state', compute_sudo=True)

    _project_partner_uniq = models.Constraint(
        'unique (project_id, partner_id)', 'This person is already on the project team.')

    @api.depends('partner_id')
    def _compute_user_id(self):
        for collaborator in self:
            users = collaborator.partner_id.with_context(active_test=False).user_ids
            collaborator.user_id = users.filtered('active')[:1] or users[:1]

    @api.depends('user_id', 'collaborator_type', 'partner_id')
    def _compute_access_state(self):
        can_manage = self.env.user.has_group(ACCESS_MANAGER_GROUP)
        for collaborator in self:
            state, message = collaborator._access_check()
            collaborator.access_state = state
            collaborator.access_message = message
            collaborator.can_fix_access = (can_manage and collaborator.collaborator_type == 'customer'
                                           and state in ('no_user', 'no_group'))

    def _access_check(self):
        """(state, message) saying whether this person can open the project."""
        self.ensure_one()
        return self.env['advanced.project.collaborator']._access_check_for(
            self.partner_id, self.collaborator_type, self.project_id)

    @api.model
    def _access_check_for(self, partner, collaborator_type, project):
        users = partner.with_context(active_test=False).user_ids
        user = users.filtered('active')[:1]
        name = partner.display_name
        if collaborator_type == 'customer':
            if not user:
                if users and users[:1]._is_internal():
                    return 'internal_user', _('%s has an archived employee login. Customers must be portal '
                                              'users; ask an administrator to sort out their user.', name)
                return 'no_user', _('%s has no portal login yet, so cannot open the project. Updating their '
                                    'permissions gives them one (an invitation email is sent).', name)
            if user._is_internal():
                return 'internal_user', _('%s is an employee user. Customers must be portal users, who only '
                                          'see their own projects: invite them as a Colleague instead, or ask '
                                          'an administrator to change them to a portal user.', name)
            if not user.has_group(CUSTOMER_GROUP):
                return 'no_group', _('%s has a portal login but not the Project Customer permission, so cannot '
                                     'open the project yet.', name)
            return 'ok', ''
        if not user or not user._is_internal():
            return 'not_employee', _('%s is not an employee user, so cannot sign in to see the project. '
                                     'Invite them as a Customer to give them portal access.', name)
        if project and not project.with_user(user).has_access('read'):
            return 'no_permission', _('%s has no Project permission that opens this project; their '
                                      'permissions have been left as they are.', name)
        return 'ok', ''

    # ------------------------------------------------------------
    # CRUD: customers follow the project, so they hear about its news
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        collaborators = super().create(vals_list)
        collaborators._follow_project()
        return collaborators

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals or 'collaborator_type' in vals:
            self._follow_project()
        return res

    def unlink(self):
        followers = {(c.project_id, c.partner_id) for c in self}
        res = super().unlink()
        for project, partner in followers:
            if project.exists():
                # sudo: removing a team member also stops their notifications
                project.sudo().message_unsubscribe(partner_ids=partner.ids)
        return res

    def _follow_project(self):
        for collaborator in self:
            # sudo: team members follow the project whatever the inviter's rights on followers
            collaborator.project_id.sudo().message_subscribe(partner_ids=collaborator.partner_id.ids)

    # ------------------------------------------------------------
    # Access
    # ------------------------------------------------------------

    def action_fix_access(self):
        """Give customers the Project Customer permission set: a portal login
        (created and invited by email when they have none) plus the Project
        Customer group, which opens only the projects they are a Customer on."""
        if not self.env.user.has_group(ACCESS_MANAGER_GROUP):
            raise AccessError(_('Only people with the "Projects: Manage Customer Access" permission can '
                                "update customers' permissions."))
        customer_group = self.env.ref(CUSTOMER_GROUP)
        for collaborator in self.filtered(lambda c: c.collaborator_type == 'customer'):
            state = collaborator.access_state
            if state == 'internal_user':
                raise UserError(collaborator.access_message)
            if state == 'no_user':
                # sudo: workflow action checked above; the portal wizard creates and invites the user
                wizard = self.env['portal.wizard'].sudo().create({'partner_ids': [(6, 0, collaborator.partner_id.ids)]})
                wizard_user = wizard.user_ids[:1]
                if not wizard_user.email:
                    raise UserError(_('%s needs an email address before they can get a portal login.',
                                      collaborator.partner_id.display_name))
                if not wizard_user.is_portal:
                    wizard_user.action_grant_access()
                collaborator.invalidate_recordset(['user_id'])
            user = collaborator.partner_id.with_context(active_test=False).user_ids.filtered('active')[:1]
            if user and not user._is_internal() and not user.has_group(CUSTOMER_GROUP):
                # sudo: workflow action checked above
                user.sudo().write({'group_ids': [(4, customer_group.id)]})
        self.invalidate_recordset(['user_id', 'access_state', 'access_message', 'can_fix_access'])
        return True

    @api.model
    def action_invite_from_context(self):
        """The Team list's Invite button: invite to the project the list is for."""
        project = self.env['advanced.project'].browse(self.env.context.get('default_project_id')).exists()
        if not project:
            raise UserError(_('Open a project to invite people to it.'))
        return project.action_invite()

    def action_send_invitation(self, message=None):
        template = self.env.ref('advanced_projects.mail_template_project_invitation', raise_if_not_found=False)
        if not template:
            return False
        for collaborator in self:
            if collaborator.partner_id.email:
                template.with_context(invitation_message=message or '').send_mail(
                    collaborator.id, email_layout_xmlid='mail.mail_notification_light')
        return True

    def _invitation_url(self):
        """Where the invitation takes them: the portal page for customers, the backend for colleagues."""
        self.ensure_one()
        base_url = self.project_id.get_base_url()
        if self.collaborator_type == 'customer':
            return f'{base_url}/my/projects/{self.project_id.id}'
        return f'{base_url}/odoo/action-advanced_projects.advanced_project_action/{self.project_id.id}'
