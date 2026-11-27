# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    laser_job_ids = fields.One2many('laser.job', 'production_id', string='Laser Jobs')
    laser_job_count = fields.Integer(compute='_compute_laser_job_count')

    @api.depends('laser_job_ids')
    def _compute_laser_job_count(self):
        for production in self:
            production.laser_job_count = len(production.sudo().laser_job_ids)

    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        productions._laser_link_jobs()
        return productions

    def _laser_link_jobs(self):
        """Pick up the laser jobs of the order a manufacturing order is made for."""
        Job = self.env['laser.job'].sudo()
        for production in self.filtered('origin'):
            jobs = Job.search([
                ('origin', '=', production.origin),
                ('product_id', '=', production.product_id.id),
                ('company_id', '=', production.company_id.id),
                ('production_id', '=', False),
                ('state', 'in', ('draft', 'confirmed')),
            ])
            if jobs:
                jobs.production_id = production

    def button_mark_done(self):
        res = super().button_mark_done()
        self.filtered(lambda p: p.state == 'done').sudo().laser_job_ids.filtered(
            lambda j: j.state in ('draft', 'confirmed', 'in_progress')).action_done()
        return res

    def action_view_laser_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('laser_jobbing.action_laser_job')
        action.update({'domain': [('production_id', '=', self.id)], 'context': {'create': False}})
        if len(self.laser_job_ids) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': self.laser_job_ids.id})
        return action


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def button_start(self, *args, **kwargs):
        res = super().button_start(*args, **kwargs)
        self.production_id.sudo().laser_job_ids.filtered(lambda j: j.state == 'confirmed').action_start()
        return res

    def _terminal_payload(self):
        payload = super()._terminal_payload()
        token = self.env.context.get('laser_terminal_token') or self.workcenter_id.sudo().terminal_token
        jobs = self.production_id.sudo().laser_job_ids.filtered(lambda j: j.state != 'cancelled')
        if not jobs or not token:
            return payload
        payload['laser_jobs'] = [{
            'id': job.id,
            'name': job.name,
            'file': '/manufacturing/workcentre/%s/laser/%s/file' % (token, job.id),
            'preview': '/manufacturing/workcentre/%s/laser/%s/preview' % (token, job.id),
        } for job in jobs if job.output_file]
        payload['instructions'] = (payload.get('instructions') or '') + self._laser_files_html(jobs, token)
        return payload

    def _laser_files_html(self, jobs, token):
        """The laser files of the order, for the Work Centre app's instructions."""
        items = []
        for job in jobs:
            base = '/manufacturing/workcentre/%s/laser/%s' % (escape(token), job.id)
            details = [escape(job.template_id.name)]
            if job.material_id:
                details.append(escape(job.material_id.name))
            details.append(escape(_('Quantity: %s', '%g' % job.quantity)))
            summary = escape(job._laser_description()).replace('\n', Markup('<br/>'))
            if job.output_file:
                file_part = Markup(
                    '<a class="btn btn-primary" href="%s/file" download="%s">%s</a>'
                    '<div><img src="%s/preview" alt="%s" style="max-width: 100%%; max-height: 240px;"/></div>'
                ) % (base, job.output_filename, _('Download %s', job.output_filename), base, job.name)
            else:
                file_part = Markup('<p><strong>%s</strong></p>') % (
                    job.output_error or _('This job has no laser file yet.'))
            settings = Markup('<p><em>%s</em></p>') % job.material_id.machine_settings \
                if job.material_id.machine_settings else Markup('')
            items.append(Markup('<li><strong>%s</strong> - %s<br/>%s%s%s</li>') % (
                job.name, Markup(' · ').join(details), summary, settings, file_part))
        return Markup('<div class="laser-files"><h4>%s</h4><ul>%s</ul></div>') % (
            _('Laser Files'), Markup('').join(items))
