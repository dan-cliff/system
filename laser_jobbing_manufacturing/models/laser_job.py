# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_config_settings import AUTO_PRODUCTION_PARAM


class LaserJob(models.Model):
    _inherit = 'laser.job'

    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', copy=False, tracking=True, index='btree_not_null',
        help='The manufacturing order this job is made in.',
    )
    production_state = fields.Selection(related='production_id.state', string='Manufacturing Status')
    has_bom = fields.Boolean(compute='_compute_has_bom')

    @api.depends('product_id')
    def _compute_has_bom(self):
        for job in self:
            job.has_bom = bool(job.product_id and self.env['mrp.bom'].sudo()._bom_find(
                job.product_id, company_id=job.company_id.id).get(job.product_id))

    @api.model
    def _laser_auto_production(self):
        value = self.env['ir.config_parameter'].sudo().get_param(AUTO_PRODUCTION_PARAM, 'True')
        return value in ('True', 'true', '1')

    def action_confirm(self):
        res = super().action_confirm()
        confirmed = self.filtered(lambda j: j.state == 'confirmed' and not j.production_id)
        confirmed._laser_link_productions()
        if self._laser_auto_production():
            confirmed.filtered(lambda j: not j.production_id and j.has_bom)._laser_create_productions()
        return res

    def _laser_link_productions(self):
        """Link jobs to the open manufacturing orders made for their order."""
        Production = self.env['mrp.production'].sudo()
        for job in self.filtered(lambda j: j.origin and j.product_id and not j.production_id):
            production = Production.search([
                ('origin', '=', job.origin),
                ('product_id', '=', job.product_id.id),
                ('company_id', '=', job.company_id.id),
                ('state', 'not in', ('done', 'cancel')),
            ], order='id', limit=1)
            if production:
                job.sudo().production_id = production

    def _laser_create_productions(self):
        for job in self:
            if not job.product_id:
                raise UserError(_('%s has no product to manufacture.', job.name))
            if not job.has_bom:
                raise UserError(_('"%s" has no bill of materials to manufacture it with.',
                                  job.product_id.display_name))
            production = self.env['mrp.production'].sudo().with_company(job.company_id).create({
                'product_id': job.product_id.id,
                'product_qty': job.quantity or 1.0,
                'product_uom_id': job.product_id.uom_id.id,
                'origin': job.origin or job.name,
                'company_id': job.company_id.id,
                'date_deadline': job.date_deadline or False,
            })
            production.action_confirm()
            job.sudo().production_id = production
            production.message_post(body=_('Made for laser job %s.', job._get_html_link()))

    def action_create_production(self):
        self.filtered(lambda j: j.state == 'draft').action_confirm()
        self.filtered(lambda j: not j.production_id)._laser_create_productions()
        return self.action_view_production()

    def action_view_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manufacturing Order'),
            'res_model': 'mrp.production',
            'view_mode': 'form',
            'res_id': self.production_id.id,
        }
