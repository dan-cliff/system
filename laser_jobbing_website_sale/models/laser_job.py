# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

UNORDERED_DAYS = 2


class LaserJob(models.Model):
    _inherit = 'laser.job'

    @api.model
    def _cron_remove_unordered_website_jobs(self):
        """Personalisations made on the website that never reached a cart line."""
        limit = fields.Datetime.now() - timedelta(days=UNORDERED_DAYS)
        jobs = self.sudo().search([
            ('source', '=', 'website'),
            ('state', '=', 'draft'),
            ('sale_line_ids', '=', False),
            ('create_date', '<', limit),
        ])
        jobs.unlink()

    def _laser_website_values(self):
        """What the product page shows about a personalisation (JSON)."""
        self.ensure_one()
        return {
            'job_id': self.id,
            'access_token': self.access_token,
            'preview_url': '%s&access_token=%s' % (self.preview_url, self.access_token) if self.preview_url else '',
            'output_format': self.output_format or '',
            'summary': self._laser_description(),
        }


class LaserTemplate(models.Model):
    _inherit = 'laser.template'

    def _laser_public_access(self):
        """The design of a template sold on the website can be shown to anyone."""
        self.ensure_one()
        return bool(self.env['product.template'].sudo().search_count([
            ('laser_template_id', '=', self.id),
            ('is_published', '=', True),
            ('sale_ok', '=', True),
        ], limit=1))
