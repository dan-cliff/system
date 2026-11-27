from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VideoProduction(models.Model):
    _inherit = 'video.production'

    project_id = fields.Many2one(
        'advanced.project', string='Project', tracking=True, index='btree_not_null', ondelete='set null',
        domain=[('is_internal', '=', True), ('is_template', '=', False)],
        help='The internal project the production is run as.')

    @api.constrains('project_id')
    def _check_project_internal(self):
        for production in self:
            # sudo: the check is about the project's type, whoever links it
            if production.project_id and not production.project_id.sudo().is_internal:
                raise ValidationError(_('"%s" can only be linked to an internal project.', production.name))

    def action_link_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project for %s', self.name),
            'res_model': 'video.production.project.link',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id},
        }

    def action_open_project(self):
        self.ensure_one()
        return self.project_id.action_open_project()


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    video_production_ids = fields.One2many('video.production', 'project_id', string='Video Productions')
    video_production_count = fields.Integer(compute='_compute_video_production_count')

    def _compute_video_production_count(self):
        Production = self.env['video.production']
        counts = {}
        if Production.has_access('read'):
            counts = dict(Production._read_group([('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        for project in self:
            project.video_production_count = counts.get(project, 0)

    def action_open_video_productions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('video_production.action_video_production')
        action.update({
            'name': _('%s – Video Productions', self.name),
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        })
        return action
