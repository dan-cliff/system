from odoo import _, fields, models


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    dashboard_ids = fields.Many2many(
        'custom.dashboard', 'advanced_project_custom_dashboard_rel', 'project_id', 'dashboard_id',
        string='Dashboards', copy=False,
        help="Dashboards to open from this project, besides those available in every project.")
    dashboard_count = fields.Integer('Dashboard Count', compute='_compute_dashboard_count')

    def _copy_plan_from(self, source, day_shift=0):
        super()._copy_plan_from(source, day_shift=day_shift)
        # sudo: the dashboards picked on a template or copied project come along,
        # also for people without access to the Dashboards app
        if source.sudo().dashboard_ids:
            self.sudo().dashboard_ids = source.sudo().dashboard_ids

    def _project_dashboards(self):
        """The dashboards this project opens that the user may see."""
        self.ensure_one()
        Dashboard = self.env['custom.dashboard']
        if not Dashboard.has_access('read'):
            return Dashboard
        return Dashboard.search(['|', ('show_in_projects', '=', True), ('id', 'in', self.dashboard_ids.ids)])

    def _compute_dashboard_count(self):
        for project in self:
            project.dashboard_count = len(project._project_dashboards()) if project.id else 0

    def action_open_dashboards(self):
        self.ensure_one()
        dashboards = self._project_dashboards()
        context = {'advanced_project_id': self.id}
        if len(dashboards) == 1:
            return dashboards.with_context(**context).action_open()
        action = self.env['ir.actions.act_window']._for_xml_id('custom_dashboard.action_custom_dashboard')
        action.update({
            'name': _('%s – Dashboards', self.name),
            'domain': [('id', 'in', dashboards.ids)],
            'context': context,
        })
        return action
