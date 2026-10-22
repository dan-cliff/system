import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LmsCourse(models.Model):
    _inherit = 'lms.course'

    scorm_course_id = fields.Many2one(
        'lms.scorm.course', string='Authored SCORM Course', tracking=True, ondelete='restrict',
        domain="[('state', '=', 'published')]",
        help='A published course from SCORM Authoring. Its package is used instead of an '
             'uploaded ZIP and is updated automatically when a new version is published.')
    scorm_course_version = fields.Integer(
        related='scorm_course_id.version_number', string='Authored Version')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('scorm_course_id'):
                vals.update(self._scorm_package_vals(vals['scorm_course_id']))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('scorm_course_id'):
            vals = dict(vals, **self._scorm_package_vals(vals['scorm_course_id']))
        return super().write(vals)

    @api.model
    def _scorm_package_vals(self, scorm_course_id):
        scorm_course = self.env['lms.scorm.course'].sudo().browse(scorm_course_id)
        if scorm_course.state != 'published':
            raise UserError(_(
                '"%s" has not been published yet, so learners cannot use it.',
                scorm_course.display_name))
        return {
            'scorm_package_id': base64.b64encode(scorm_course._build_package()),
            'scorm_package_filename': scorm_course._package_filename(),
            'scorm_launch_file': 'index.html',
            'passing_score': scorm_course.passing_score,
            'delivery_mode': 'scorm',
        }

    @api.onchange('scorm_course_id')
    def _onchange_scorm_course_id(self):
        if self.scorm_course_id:
            self.delivery_mode = 'scorm'
            self.scorm_launch_file = 'index.html'
            self.passing_score = self.scorm_course_id.passing_score
            if not self.name:
                self.name = self.scorm_course_id.name

    def action_refresh_scorm_package(self):
        for course in self.filtered('scorm_course_id'):
            course.write({'scorm_course_id': course.scorm_course_id.id})
        return True

    def action_open_scorm_course(self):
        self.ensure_one()
        return self.scorm_course_id.action_open_form()
