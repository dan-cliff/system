from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

MANAGER_GROUP = 'custom_dashboard.group_dashboard_manager'


def sitemap_dashboards(env, rule, qs):
    if not qs or qs.lower() in '/dashboards':
        yield {'loc': '/dashboards'}
    website = env['website'].get_current_website()
    dashboards = env['custom.dashboard'].sudo().search(
        [('is_published', '=', True)] + list(website.website_domain())
    )
    for dashboard in dashboards:
        loc = dashboard.website_url
        if not qs or qs.lower() in loc:
            yield {'loc': loc}


class CustomDashboardWebsite(http.Controller):

    def _get_published_dashboard(self, dashboard_id):
        """Return the dashboard (sudo) if the visitor may see it, else 404.

        Unpublished dashboards are only shown to dashboard managers, so
        they can preview a page before publishing it.
        """
        dashboard = request.env['custom.dashboard'].sudo().browse(int(dashboard_id)).exists()
        if not dashboard or not dashboard.active or not dashboard.can_access_from_current_website():
            raise NotFound()
        if not dashboard.is_published and not request.env.user.has_group(MANAGER_GROUP):
            raise NotFound()
        return dashboard

    @http.route('/dashboards', type='http', auth='public', website=True, sitemap=sitemap_dashboards, readonly=True)
    def dashboards(self, **kw):
        website = request.website
        dashboards = request.env['custom.dashboard'].sudo().search(
            [('is_published', '=', True)] + list(website.website_domain())
        )
        return request.render('custom_dashboard_website.dashboard_index', {'dashboards': dashboards})

    @http.route('/dashboards/<string:slug>', type='http', auth='public',
                website=True, sitemap=False, readonly=True)
    def dashboard_page(self, slug, **kw):
        # Visitors cannot read dashboards, so resolve the slug with sudo
        # rather than through the model converter.
        _name, dashboard_id = request.env['ir.http']._unslug(slug)
        if not dashboard_id:
            raise NotFound()
        dashboard = self._get_published_dashboard(dashboard_id)
        if slug != dashboard.website_url.rsplit('/', 1)[-1]:
            return request.redirect(dashboard.website_url, code=301)
        return request.render('custom_dashboard_website.dashboard_page', {
            'dashboard': dashboard,
            'main_object': dashboard,
            'can_edit': request.env.user.has_group(MANAGER_GROUP),
        })

    @http.route('/dashboards/data', type='jsonrpc', auth='public', website=True, readonly=True)
    def dashboard_data(self, dashboard_id):
        return self._get_published_dashboard(dashboard_id)._get_public_dashboard()

    @http.route('/dashboards/<int:dashboard_id>/image/<int:widget_id>', type='http', auth='public',
                website=True, sitemap=False, readonly=True)
    def dashboard_image(self, dashboard_id, widget_id, **kw):
        dashboard = self._get_published_dashboard(dashboard_id)
        widget = dashboard.widget_ids.filtered(lambda w: w.id == widget_id)
        if not widget or not widget.image:
            raise NotFound()
        return request.env['ir.binary']._get_image_stream_from(widget, 'image').get_response()
