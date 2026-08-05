from odoo import models, fields, api


class LmsCourseCategory(models.Model):
    _name = 'lms.course.category'
    _description = 'LMS Course Category'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True, translate=True)
    color = fields.Integer(string='Colour', default=0)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')
    course_ids = fields.One2many('lms.course', 'category_id', string='Courses')
    course_count = fields.Integer(string='Course Count', compute='_compute_course_count')

    @api.depends('course_ids')
    def _compute_course_count(self):
        for rec in self:
            rec.course_count = len(rec.course_ids)
