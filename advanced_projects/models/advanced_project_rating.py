from odoo import _, api, fields, models
from odoo.exceptions import UserError

# A fixed 1 to 5 star scale (shown as stars, and averaged), so a technical
# selection rather than an option model (CLAUDE.md > Choice fields).
RATING_SCORES = [
    ('0', 'Not Rated'),
    ('1', 'Poor'),
    ('2', 'Fair'),
    ('3', 'Good'),
    ('4', 'Very Good'),
    ('5', 'Excellent'),
]


class AdvancedProjectRating(models.Model):
    """A rating of a project (or one of its tasks), given at any point of the
    project: entered by staff, or submitted by the person asked through the
    portal link (``rating_url``) of a requested rating. Ratings are requested
    when a task set to "Request a Rating on Completion" is done; sending the
    request is left to Workflow Automation (e.g. an email on creation of a
    rating with Status "Requested", linking to its Rating Link)."""
    _name = 'advanced.project.rating'
    _description = 'Project Rating'
    _inherit = ['portal.mixin', 'mail.thread']
    _order = 'date_requested desc, id desc'

    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade',
        domain=[('is_template', '=', False)], tracking=True)
    task_id = fields.Many2one(
        'advanced.project.task', string='Task', index='btree_not_null', ondelete='set null',
        domain="[('project_id', '=', project_id)]", tracking=True)
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Rated By', index='btree_not_null', tracking=True,
        help='Who gives the rating (for a requested rating: who is asked).')
    requested_by_id = fields.Many2one(
        'res.users', string='Requested By', default=lambda self: self.env.user, readonly=True)
    # Technical workflow state: Requested until the rating is given.
    state = fields.Selection(
        [('requested', 'Requested'), ('done', 'Rated')], string='Status', required=True,
        default='done', tracking=True, index=True)
    score = fields.Selection(RATING_SCORES, string='Rating', default='0', required=True, tracking=True)
    score_value = fields.Integer('Score', compute='_compute_score_value', store=True, aggregator='avg')
    feedback = fields.Text()
    date_requested = fields.Datetime('Requested On', default=fields.Datetime.now, readonly=True)
    date_rated = fields.Datetime('Rated On', readonly=True, copy=False)
    rating_url = fields.Char(
        'Rating Link', compute='_compute_rating_url',
        help='Where the person asked gives the rating: use it in the request sent by Workflow Automation.')

    @api.depends('score')
    def _compute_score_value(self):
        for rating in self:
            rating.score_value = int(rating.score or 0)

    @api.depends('project_id', 'task_id', 'partner_id')
    def _compute_display_name(self):
        for rating in self:
            subject = rating.task_id.name or rating.project_id.name or ''
            rating.display_name = _('%(subject)s – %(partner)s', subject=subject, partner=rating.partner_id.name) \
                if rating.partner_id else subject

    def _compute_access_url(self):
        super()._compute_access_url()
        for rating in self:
            rating.access_url = f'/my/projects/rating/{rating.id}'

    def _compute_rating_url(self):
        for rating in self:
            rating.rating_url = rating.id and rating.get_base_url() + rating.sudo().get_portal_url() or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('task_id') and not vals.get('project_id'):
                vals['project_id'] = self.env['advanced.project.task'].browse(vals['task_id']).project_id.id
            if vals.get('state', 'done') == 'done' and vals.get('score', '0') != '0':
                vals.setdefault('date_rated', fields.Datetime.now())
        ratings = super().create(vals_list)
        ratings.sudo()._portal_ensure_token()
        return ratings

    def write(self, vals):
        if vals.get('score', '0') != '0' and 'date_rated' not in vals:
            vals = dict(vals, date_rated=fields.Datetime.now())
            vals.setdefault('state', 'done')
        return super().write(vals)

    def _submit(self, score, feedback=None):
        """Give the rating (from the portal link or the form)."""
        self.ensure_one()
        if str(score) not in {value for value, _label in RATING_SCORES[1:]}:
            raise UserError(_('Choose a rating from 1 to 5 stars.'))
        self.write({'score': str(score), 'feedback': feedback or self.feedback, 'state': 'done'})


class AdvancedProjectTask(models.Model):
    _inherit = 'advanced.project.task'

    request_rating = fields.Boolean(
        'Request a Rating on Completion', tracking=True,
        help='When the task is done, ask the contact below to rate it (the request is sent by Workflow '
             'Automation).')
    rating_partner_id = fields.Many2one(
        'res.partner', string='Ask for a Rating From', compute='_compute_rating_partner_id', store=True,
        readonly=False, help="Who is asked to rate the task. Defaults to the project's customer.")
    project_rating_ids = fields.One2many('advanced.project.rating', 'task_id', string='Ratings')

    @api.depends('request_rating', 'project_id.partner_id')
    def _compute_rating_partner_id(self):
        for task in self:
            if task.request_rating and not task.rating_partner_id:
                task.rating_partner_id = task.project_id.partner_id

    def _request_ratings(self):
        """Request a rating for the tasks just done that ask for one (once per
        task and contact)."""
        tasks = self.filtered(lambda t: t.request_rating and t.rating_partner_id and t.stage_category == 'done')
        if not tasks:
            return
        # sudo: a workflow step of completing the task
        Rating = self.env['advanced.project.rating'].sudo()
        requested = {(r.task_id, r.partner_id) for r in Rating.search([('task_id', 'in', tasks.ids)])}
        Rating.create([{
            'project_id': task.project_id.id,
            'task_id': task.id,
            'partner_id': task.rating_partner_id.id,
            'state': 'requested',
        } for task in tasks.sudo() if (task, task.rating_partner_id) not in requested])

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._request_ratings()
        return tasks

    def write(self, vals):
        done_before = self.filtered(lambda t: t.stage_category == 'done') if 'stage_id' in vals else self
        res = super().write(vals)
        if 'stage_id' in vals:
            (self - done_before)._request_ratings()
        return res


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    project_rating_ids = fields.One2many('advanced.project.rating', 'project_id', string='Ratings')
    project_rating_count = fields.Integer('Ratings', compute='_compute_rating_stats')
    project_rating_avg = fields.Float('Average Rating', compute='_compute_rating_stats', digits=(2, 1))

    def _compute_rating_stats(self):
        Rating = self.env['advanced.project.rating']
        stats = {project: (count, avg) for project, count, avg in Rating._read_group(
            [('project_id', 'in', self.ids), ('state', '=', 'done'), ('score', '!=', '0')],
            ['project_id'], ['__count', 'score_value:avg'])}
        for project in self:
            project.project_rating_count, project.project_rating_avg = stats.get(project, (0, 0.0))

    def action_open_ratings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_projects.advanced_project_rating_action')
        action.update({
            'name': _('%s – Ratings', self.name),
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        })
        return action
