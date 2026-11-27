# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    laser_job_count = fields.Integer(compute='_compute_laser_jobs')
    laser_jobs_missing = fields.Boolean(
        compute='_compute_laser_jobs',
        help='Some personalised products have no laser job yet.',
    )

    @api.depends('order_line.laser_job_id', 'order_line.product_id')
    def _compute_laser_jobs(self):
        for order in self:
            lines = order.order_line._laser_lines()
            order.laser_job_count = len(lines.laser_job_id)
            order.laser_jobs_missing = bool(lines.filtered(lambda line: not line.laser_job_id))

    def action_view_laser_jobs(self):
        self.ensure_one()
        jobs = self.order_line.laser_job_id
        action = self.env['ir.actions.act_window']._for_xml_id('laser_jobbing.action_laser_job')
        action.update({'domain': [('id', 'in', jobs.ids)], 'context': {'create': False}})
        if len(jobs) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': jobs.id})
        return action

    def action_laser_personalise(self):
        """Make the laser jobs now, to fill them in before the order is confirmed."""
        self._laser_prepare_jobs()
        return self.action_view_laser_jobs()

    def action_confirm(self):
        # Jobs exist (with the order as their origin) before the order's
        # procurements run, so manufacturing orders can find them.
        self._laser_prepare_jobs()
        res = super().action_confirm()
        self._laser_confirm_jobs()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        self.order_line.laser_job_id.sudo().filtered(lambda job: job.state != 'done').action_cancel()
        return res

    def _laser_prepare_jobs(self):
        """A laser job for every personalised line, kept in step with the line."""
        for line in self.order_line._laser_lines():
            values = line._laser_job_values()
            job = line.laser_job_id.sudo()
            if job:
                if job.state in ('draft', 'confirmed'):
                    job.write({k: v for k, v in values.items() if job[k] != v and k != 'template_id'})
            else:
                job = self.env['laser.job'].sudo().with_company(line.company_id).create(values)
                line.sudo().laser_job_id = job

    def _laser_confirm_jobs(self):
        """Confirm the jobs that are filled in; note the ones still missing details."""
        for order in self:
            missing = []
            for job in order.order_line.laser_job_id.sudo().filtered(lambda j: j.state == 'draft'):
                try:
                    with self.env.cr.savepoint():
                        job.action_confirm()
                except UserError as error:
                    missing.append('%s: %s' % (job.name, error.args[0]))
                    job.message_post(body=_('Not confirmed with %(order)s: %(reason)s',
                                            order=order.name, reason=error.args[0]))
            if missing:
                order.message_post(body=_(
                    'These laser jobs need their personalisation before they can be made: %s',
                    '; '.join(missing),
                ))


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    laser_job_id = fields.Many2one(
        'laser.job', string='Laser Job', copy=False, index='btree_not_null',
        domain="[('product_id', '=', product_id)]",
        help='The personalisation of this line and the file for the laser.',
    )
    laser_template_id = fields.Many2one(related='product_id.laser_template_id', string='Laser Template')

    def _laser_lines(self):
        return self.filtered(lambda line: not line.display_type and line.product_id.laser_template_id)

    def _laser_job_values(self):
        self.ensure_one()
        order = self.order_id
        return {
            'template_id': self.product_id.laser_template_id.id,
            'product_id': self.product_id.id,
            'quantity': self.product_uom_qty,
            'partner_id': order.partner_shipping_id.id or order.partner_id.id,
            'origin': order.name,
            'company_id': order.company_id.id,
            'date_deadline': order.commitment_date or False,
            'user_id': False,
        }

    def write(self, vals):
        res = super().write(vals)
        if 'product_uom_qty' in vals:
            for line in self.filtered('laser_job_id'):
                job = line.laser_job_id.sudo()
                if job.state in ('draft', 'confirmed') and job.quantity != line.product_uom_qty:
                    job.quantity = line.product_uom_qty
        return res
