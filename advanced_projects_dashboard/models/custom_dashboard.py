from odoo import _, api, fields, models
from odoo.exceptions import UserError

PROJECT_MODEL = 'advanced.project'
# The context key a dashboard opened from a project carries.
PROJECT_KEY = 'advanced_project_id'


class CustomDashboard(models.Model):
    _inherit = 'custom.dashboard'

    show_in_projects = fields.Boolean(
        'Available in Projects',
        help='Show this dashboard on every project (its Dashboards smart button). It can also be picked '
             'for single projects on their Dashboards tab. Opened from a project, widgets with a Project '
             'Field only show that project\'s records.')

    def action_open(self):
        action = super().action_open()
        project_id = self.env.context.get(PROJECT_KEY)
        if project_id:
            project = self.env[PROJECT_MODEL].browse(project_id).exists()
            if project:
                project.check_access('read')
                action['name'] = _('%(dashboard)s – %(project)s', dashboard=self.name, project=project.name)
                action['params'] = dict(action.get('params') or {}, **{PROJECT_KEY: project.id})
                action['context'] = dict(action.get('context') or {}, **{PROJECT_KEY: project.id})
        return action


class CustomDashboardWidget(models.Model):
    _inherit = 'custom.dashboard.widget'

    project_field_path = fields.Char(
        'Project Field',
        help='The field on these records that holds the project (e.g. Project, or Project Task › Project). '
             'When the dashboard is opened from a project, the widget only shows that project\'s records; '
             'opened from the Dashboards app it is not filtered. Leave empty to never filter by project.')

    @api.onchange('model_id')
    def _onchange_model_id_project(self):
        for widget in self:
            widget.project_field_path = widget._guess_project_field_path()

    def _guess_project_field_path(self):
        """The likeliest path to the project on the widget's model."""
        self.ensure_one()
        if not self.model_name or self.model_name not in self.env:
            return False
        if self.model_name == PROJECT_MODEL:
            return 'id'
        fields_ = self.env[self.model_name]._fields
        direct = [name for name, field in fields_.items()
                  if field.type == 'many2one' and field.comodel_name == PROJECT_MODEL and field.store]
        if direct:
            return 'project_id' if 'project_id' in direct else sorted(direct)[0]
        for name, field in sorted(fields_.items()):
            if field.type == 'many2one' and field.comodel_name == 'advanced.project.task' and field.store:
                return f'{name}.project_id'
        return False

    def _get_domain(self, data_env=None):
        domain = super()._get_domain(data_env)
        env = data_env if data_env is not None else self.env
        project_id = env.context.get(PROJECT_KEY) or self.env.context.get(PROJECT_KEY)
        if project_id and self.project_field_path and self.model_name in env:
            path = self.project_field_path
            try:
                env[self.model_name]._search([(path, '=', int(project_id))])
            except (ValueError, KeyError) as error:
                raise UserError(_('The Project Field "%(path)s" of widget "%(name)s" is not valid: %(error)s',
                                  path=path, name=self.name, error=error))
            domain = domain + [(path, '=', int(project_id))]
        return domain
