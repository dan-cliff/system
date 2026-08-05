# -*- coding: utf-8 -*-
from odoo import http


class ZyraWebManager(http.Controller):
    @http.route('/zyra_rest_api_manager/zyra_rest_api_manager', auth='public')
    def index(self, **kw):
        return "Hello, world"

    @http.route('/zyra_rest_api_manager/zyra_rest_api_manager/objects', auth='public')
    def list(self, **kw):
        return http.request.render('zyra_rest_api_manager.listing', {
            'root': '/zyra_rest_api_manager/zyra_rest_api_manager',
            'objects': http.request.env['zyra_rest_api_manager.zyra_rest_api_manager'].search([]),
        })

    @http.route('/zyra_rest_api_manager/zyra_rest_api_manager/objects/<model("zyra_rest_api_manager.zyra_rest_api_manager"):obj>', auth='public')
    def object(self, obj, **kw):
        return http.request.render('zyra_rest_api_manager.object', {
            'object': obj
        })

