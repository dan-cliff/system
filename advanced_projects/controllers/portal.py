from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..models.advanced_project_task_filter import format_date


class AdvancedProjectCustomerPortal(CustomerPortal):
    """Customers follow their projects at /my/projects: the plan (phases and the
    tasks shared with customers), published updates, the team and the chatter
    (Private comments stay hidden from them)."""

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'advanced_project_count' in counters:
            Project = request.env['advanced.project']
            values['advanced_project_count'] = (
                Project.search_count([('is_template', '=', False)]) if Project.has_access('read') else 0)
        return values

    def _project_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name'},
            'end': {'label': _('Target End Date'), 'order': 'date_end'},
        }

    @http.route(['/my/projects', '/my/projects/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_projects(self, page=1, sortby=None, **kw):
        Project = request.env['advanced.project']
        if not Project.has_access('read'):
            return request.redirect('/my')
        sortings = self._project_searchbar_sortings()
        sortby = sortby if sortby in sortings else 'date'
        domain = Domain('is_template', '=', False)
        count = Project.search_count(domain)
        pager = portal_pager(url='/my/projects', url_args={'sortby': sortby}, total=count, page=page,
                             step=self._items_per_page)
        projects = Project.search(domain, order=sortings[sortby]['order'], limit=self._items_per_page,
                                  offset=pager['offset'])
        request.session['my_advanced_projects_history'] = projects.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'projects': projects,
            'page_name': 'advanced_project',
            'default_url': '/my/projects',
            'pager': pager,
            'searchbar_sortings': sortings,
            'sortby': sortby,
            'format_date': format_date,
        })
        return request.render('advanced_projects.portal_my_projects', values)

    def _project_page_values(self, project_sudo, **kw):
        tasks = project_sudo.task_ids.filtered('customer_visible')
        phases = []
        for phase in project_sudo.phase_ids:
            phases.append({'phase': phase, 'tasks': tasks.filtered(lambda t: t.phase_id == phase)})
        unphased = tasks.filtered(lambda t: not t.phase_id)
        updates = project_sudo.update_ids.filtered(lambda u: u.state == 'published' and u.customer_visible)
        return {
            'page_name': 'advanced_project',
            'project': project_sudo,
            'phases': phases,
            'unphased_tasks': unphased,
            'updates': updates,
            'team': project_sudo.collaborator_ids,
            'format_date': format_date,
        }

    @http.route('/my/projects/<int:project_id>', type='http', auth='public', website=True)
    def portal_my_project(self, project_id, access_token=None, **kw):
        try:
            project_sudo = self._document_check_access('advanced.project', project_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if project_sudo.is_template:
            return request.redirect('/my')
        values = self._project_page_values(project_sudo, **kw)
        values = self._get_page_view_values(
            project_sudo, access_token, values, 'my_advanced_projects_history', False, **kw)
        return request.render('advanced_projects.portal_my_project', values)

    @http.route('/my/projects/<int:project_id>/tasks/<int:task_id>', type='http', auth='public', website=True)
    def portal_my_project_task(self, project_id, task_id, access_token=None, **kw):
        try:
            task_sudo = self._document_check_access('advanced.project.task', task_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if task_sudo.project_id.id != project_id or not task_sudo.customer_visible:
            return request.redirect('/my')
        values = {
            'page_name': 'advanced_project_task',
            'project': task_sudo.project_id,
            'task': task_sudo,
            'format_date': format_date,
        }
        values = self._get_page_view_values(task_sudo, access_token, values, False, True, **kw)
        return request.render('advanced_projects.portal_my_project_task', values)

    @http.route('/my/projects/<int:project_id>/updates/<int:update_id>', type='http', auth='public', website=True)
    def portal_my_project_update(self, project_id, update_id, access_token=None, **kw):
        try:
            update_sudo = self._document_check_access('advanced.project.update', update_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if (update_sudo.project_id.id != project_id or update_sudo.state != 'published'
                or not update_sudo.customer_visible):
            return request.redirect('/my')
        values = {
            'page_name': 'advanced_project_update',
            'project': update_sudo.project_id,
            'update': update_sudo,
            'format_date': format_date,
        }
        values = self._get_page_view_values(update_sudo, access_token, values, False, True, **kw)
        return request.render('advanced_projects.portal_my_project_update', values)
