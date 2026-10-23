from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LmsScormSlideSet(models.Model):
    """Slides that go at the start or end of every course (e.g. a welcome,
    a safety acknowledgement, a feedback slide).

    The slides are designed in the SCORM editor: each set keeps them on a
    hidden template course (``is_slide_set``) that never reaches learners.
    """
    _name = 'lms.scorm.slide.set'
    _description = 'SCORM Standard Slide Set'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company,
        help='Leave empty to offer the set to every company.')
    is_default = fields.Boolean(
        string='Add to New Courses',
        help='New courses get these slides automatically (one default per company).')
    lock_slides = fields.Boolean(
        string='Lock in Courses', default=True,
        help='Authors cannot change, move or delete these slides in their courses. '
             'Update the set instead, then use "Update Standard Slides" on a course.')
    description = fields.Text(string='Notes')
    template_course_id = fields.Many2one(
        'lms.scorm.course', string='Slides', readonly=True, copy=False, ondelete='restrict')
    slide_count = fields.Integer(compute='_compute_slide_count', string='Slides in Set')
    start_slide_count = fields.Integer(compute='_compute_slide_count', string='At the Start')
    end_slide_count = fields.Integer(compute='_compute_slide_count', string='At the End')
    course_count = fields.Integer(compute='_compute_course_count', string='Courses')

    def _compute_slide_count(self):
        for slide_set in self:
            slides = slide_set.template_course_id.sudo().slide_ids
            slide_set.slide_count = len(slides)
            slide_set.start_slide_count = len(slides.filtered(lambda s: s.standard_position == 'start'))
            slide_set.end_slide_count = len(slides) - slide_set.start_slide_count

    def _compute_course_count(self):
        Course = self.env['lms.scorm.course'].sudo().with_context(active_test=False)
        for slide_set in self:
            slide_set.course_count = Course.search_count([('slide_set_id', '=', slide_set.id)]) if slide_set.id else 0

    @api.model_create_multi
    def create(self, vals_list):
        sets = super().create(vals_list)
        for slide_set in sets:
            slide_set.template_course_id = self.env['lms.scorm.course'].sudo().with_context(
                scorm_no_standard_slides=True).create({
                    'name': _('Standard slides: %s', slide_set.name),
                    'is_slide_set': True,
                    'company_id': slide_set.company_id.id or self.env.company.id,
                })
        sets._check_single_default()
        return sets

    def write(self, vals):
        result = super().write(vals)
        if 'name' in vals:
            for slide_set in self:
                slide_set.template_course_id.sudo().name = _('Standard slides: %s', slide_set.name)
        if vals.get('is_default') or 'company_id' in vals:
            self._check_single_default()
        return result

    def unlink(self):
        templates = self.template_course_id
        result = super().unlink()
        templates.sudo().with_context(active_test=False).unlink()
        return result

    def _check_single_default(self):
        """One default per company: making this one the default unsets the others."""
        for slide_set in self.filtered('is_default'):
            others = self.search([
                ('id', '!=', slide_set.id), ('is_default', '=', True),
                ('company_id', '=', slide_set.company_id.id),
            ])
            others.write({'is_default': False})

    @api.model
    def _default_for_company(self, company):
        return self.search([('is_default', '=', True), ('company_id', 'in', [company.id, False])],
                           order='company_id desc, sequence', limit=1)

    def action_edit_slides(self):
        self.ensure_one()
        return self.template_course_id.action_open_editor()

    def action_preview(self):
        self.ensure_one()
        return self.template_course_id.action_preview()

    def action_view_courses(self):
        self.ensure_one()
        return {
            'name': _('Courses using %s', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.course',
            'view_mode': 'list,form',
            'domain': [('slide_set_id', '=', self.id)],
        }

    def action_apply_to_drafts(self):
        """Bring every draft course using this set up to date with it."""
        self.ensure_one()
        courses = self.env['lms.scorm.course'].search(
            [('slide_set_id', '=', self.id), ('state', '=', 'draft'), ('is_slide_set', '=', False)])
        if not courses:
            raise UserError(_('No draft course uses this set.'))
        for course in courses:
            course._apply_slide_set()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Standard slides updated in %s draft course(s). Published courses '
                             'get them in their next version.', len(courses)),
            },
        }
