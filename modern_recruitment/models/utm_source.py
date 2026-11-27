# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import UserError


class UtmSource(models.Model):
    _inherit = 'utm.source'

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_recruitment_sources(self):
        # Recruitment's check, with Talent in its message.
        linked_recruitment_sources = self.env['hr.recruitment.source'].sudo().search([
            ('source_id', 'in', self.ids)
        ])
        if linked_recruitment_sources:
            raise UserError(self.env._(
                "You cannot delete these UTM Sources as they are linked to the following recruitment sources in "
                "Talent:\n%(recruitment_sources)s",
                recruitment_sources=', '.join(['"%s"' % name for name in linked_recruitment_sources.job_id.mapped('name')])))
