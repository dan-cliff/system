# -*- coding: utf-8 -*-
"""Inventory Signage: digital signs full screen on any screen.

The signage PWA runs on a screen logged in to Odoo (no secrets in addresses).
Raspberry Pi Nodes use advanced_inventory_iot's signed routes instead.

Routes:
    GET /inventory/signage                       PWA start page: the signs this user can open
    GET /inventory/signage/<id>                  A sign, full screen
    GET /inventory/signage/<id>/content          The sign as JSON (polled)
    GET /inventory/signage/design/<id>           Full-screen preview of a sign design
    GET /inventory/signage/design/<id>/content
    GET /inventory/signage/manifest.webmanifest  PWA manifest (no data)
    GET /inventory/signage/sw.js                 Service worker: keeps the last sign on screen offline
"""
import json

from odoo import http
from odoo.http import request
from odoo.tools import file_open


def _json(data, status=200):
    return request.make_response(json.dumps(data), status=status, headers=[
        ('Content-Type', 'application/json'), ('Cache-Control', 'no-store')])


class InventorySignageController(http.Controller):

    @http.route('/inventory/signage/manifest.webmanifest', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def manifest(self, **kwargs):
        manifest = {
            'name': 'Inventory Signage',
            'short_name': 'Signage',
            'description': 'Warehouse digital signs: warehouses, rooms, aisles, shelves and totes.',
            'start_url': '/inventory/signage',
            'scope': '/inventory/signage',
            'display': 'fullscreen',
            'orientation': 'any',
            'background_color': '#0f1218',
            'theme_color': '#5B3DB8',
            'icons': [
                {'src': '/advanced_inventory/static/description/signage_192.png', 'sizes': '192x192', 'type': 'image/png'},
                {'src': '/advanced_inventory/static/description/signage_512.png', 'sizes': '512x512', 'type': 'image/png'},
                {'src': '/advanced_inventory/static/description/signage_512.png', 'sizes': '512x512', 'type': 'image/png',
                 'purpose': 'maskable'},
            ],
        }
        return request.make_response(json.dumps(manifest), headers=[('Content-Type', 'application/manifest+json')])

    @http.route('/inventory/signage/sw.js', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def service_worker(self, **kwargs):
        with file_open('advanced_inventory/static/src/signage/sw.js', 'rb') as file:
            body = file.read()
        return request.make_response(body, headers=[
            ('Content-Type', 'text/javascript'),
            ('Service-Worker-Allowed', '/inventory/signage/'),
            ('Cache-Control', 'no-cache'),
        ])

    @http.route('/inventory/signage', type='http', auth='user', methods=['GET'])
    def picker(self, **kwargs):
        signs = request.env['advanced.inventory.sign'].search([])
        return request.render('advanced_inventory.signage_picker', {'signs': signs})

    @http.route('/inventory/signage/<int:sign_id>', type='http', auth='user', methods=['GET'])
    def sign_page(self, sign_id, **kwargs):
        sign = request.env['advanced.inventory.sign'].browse(sign_id).exists()
        if not sign:
            return request.not_found()
        return request.render('advanced_inventory.signage_page', {
            'title': sign.name, 'content_url': '/inventory/signage/%s/content' % sign.id, 'pwa': True})

    @http.route('/inventory/signage/<int:sign_id>/content', type='http', auth='user', methods=['GET'])
    def sign_content(self, sign_id, **kwargs):
        sign = request.env['advanced.inventory.sign'].browse(sign_id).exists()
        if not sign:
            return _json({'status': 'error', 'message': 'This sign no longer exists.'}, 404)
        sign._sign_seen()
        return _json(dict(sign._sign_content(), status='ok'))

    @http.route('/inventory/signage/design/<int:template_id>', type='http', auth='user', methods=['GET'])
    def design_page(self, template_id, **kwargs):
        template = request.env['advanced.inventory.sign.template'].browse(template_id).exists()
        if not template:
            return request.not_found()
        return request.render('advanced_inventory.signage_page', {
            'title': template.name, 'content_url': '/inventory/signage/design/%s/content' % template.id, 'pwa': False})

    @http.route('/inventory/signage/design/<int:template_id>/content', type='http', auth='user', methods=['GET'])
    def design_content(self, template_id, **kwargs):
        template = request.env['advanced.inventory.sign.template'].browse(template_id).exists()
        if not template:
            return _json({'status': 'error', 'message': 'This sign design no longer exists.'}, 404)
        sign = request.env['advanced.inventory.sign'].new({
            'name': template.name, 'template_id': template.id, 'refresh_seconds': 30})
        record = template._design_sample_record()
        if template.target == 'warehouse':
            sign.warehouse_id = record
        elif template.target == 'product':
            sign.product_id = record
        else:
            sign.location_id = record
        return _json(dict(sign._sign_content(), status='ok'))
