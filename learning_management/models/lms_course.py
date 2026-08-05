from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class LmsCourse(models.Model):
    _name = 'lms.course'
    _description = 'LMS Course'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Course Name', required=True, tracking=True, translate=True)
    code = fields.Char(string='Code', copy=False)
    category_id = fields.Many2one('lms.course.category', string='Category', ondelete='set null')
    course_type = fields.Selection([
        ('licence', 'Licence'),
        ('qualification', 'Qualification'),
        ('training', 'Training'),
        ('elearning', 'eLearning'),
    ], string='Type', required=True, tracking=True)
    delivery_mode = fields.Selection([
        ('in_person', 'In Person'),
        ('scorm', 'SCORM Package'),
        ('google_slides', 'Google Slides / Presentation'),
        ('document', 'Document / Reading'),
        ('upload', 'Employee Upload Only'),
    ], string='Delivery Mode', required=True, tracking=True)
    description = fields.Html(string='Description', sanitize=True)
    duration_hours = fields.Float(string='Duration (Hours)', digits=(6, 2))
    cost = fields.Monetary(
        string='Cost',
        currency_field='currency_id',
        help='Per-employee cost for this course (e.g. external training fee).',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    validity_months = fields.Integer(
        string='Validity (Months)',
        help='Number of months this qualification/licence is valid. 0 means no expiry.'
    )

    # SCORM content
    scorm_package_id = fields.Binary(
        string='SCORM Package (ZIP)',
        attachment=True,
        help='Upload a SCORM 1.2 or SCORM 2004 compliant ZIP package.',
    )
    scorm_package_filename = fields.Char(string='SCORM Package Filename')
    scorm_launch_file = fields.Char(
        string='SCORM Launch File',
        help='Relative path to the launch file inside the SCORM ZIP (e.g. index.html). '
             'Leave blank to auto-detect from imsmanifest.xml.',
    )
    passing_score = fields.Integer(string='Passing Score (%)', default=80)

    # Google Slides / presentation content
    google_slides_url = fields.Char(
        string='Presentation URL',
        help='Google Slides, PowerPoint Online, or any embeddable presentation URL. '
             'For Google Slides use the /embed version of the URL.',
    )
    slide_count = fields.Integer(
        string='Number of Slides',
        default=0,
        help='Total number of slides in this presentation. '
             'When set, employees must navigate through every slide before they can '
             'mark the training as complete. Set to 0 to use a simple confirmation '
             'checkbox instead (no page-by-page tracking).',
    )

    # Supporting documents
    document_ids = fields.Many2many(
        'ir.attachment',
        'lms_course_doc_rel',
        'course_id',
        'attachment_id',
        string='Supporting Documents',
    )

    # Image / thumbnail
    image = fields.Image(string='Thumbnail', max_width=256, max_height=256)

    # Flags
    requires_upload = fields.Boolean(
        string='Requires Proof Upload',
        help='Employee must upload supporting document (e.g. certificate) to mark complete.',
    )
    is_mandatory = fields.Boolean(string='Mandatory', tracking=True)
    active = fields.Boolean(default=True)

    # Assessment
    assessment_template_id = fields.Many2one(
        'lms.assessment.template', string='Assessment Template',
        ondelete='set null',
        help='Assessment template employees must complete as part of this course.'
    )
    requires_assessment = fields.Boolean(
        string='Requires Assessment for Completion',
        help='If enabled, employees must pass the linked assessment before the course record can be marked complete.'
    )

    # Relationships
    session_ids = fields.One2many('lms.course.session', 'course_id', string='Sessions')
    session_count = fields.Integer(string='Sessions', compute='_compute_session_count')
    record_count = fields.Integer(string='Employee Records', compute='_compute_record_count')
    group_ids = fields.Many2many(
        'lms.course.group',
        'lms_course_group_course_rel',
        'course_id',
        'group_id',
        string='Course Groups',
    )

    @api.depends('session_ids')
    def _compute_session_count(self):
        for rec in self:
            rec.session_count = len(rec.session_ids)

    def _compute_record_count(self):
        for rec in self:
            rec.record_count = self.env['lms.employee.record'].search_count([('course_id', '=', rec.id)])

    @api.constrains('delivery_mode', 'scorm_package_id', 'google_slides_url')
    def _check_content(self):
        for rec in self:
            if rec.delivery_mode == 'scorm' and not rec.scorm_package_id:
                raise ValidationError(_('A SCORM Package must be uploaded for SCORM delivery mode.'))
            if rec.delivery_mode == 'google_slides' and not rec.google_slides_url:
                raise ValidationError(_('A presentation URL must be provided for Google Slides / Presentation delivery.'))

    @api.onchange('assessment_template_id')
    def _onchange_assessment_template_id(self):
        if self.assessment_template_id:
            self.requires_assessment = True

    @api.onchange('course_type')
    def _onchange_course_type(self):
        """Suggest a sensible delivery mode when the type changes."""
        if self.course_type in ('licence', 'qualification'):
            self.delivery_mode = 'upload'
            self.requires_upload = True
        elif self.course_type == 'training':
            self.delivery_mode = 'in_person'
        elif self.course_type == 'elearning':
            self.delivery_mode = 'scorm'

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'name': _('Sessions — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.course.session',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {'default_course_id': self.id},
        }

    def action_view_records(self):
        self.ensure_one()
        return {
            'name': _('Employee Records — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.employee.record',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {'default_course_id': self.id},
        }
