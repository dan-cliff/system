import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .lms_scorm_course import EDITABLE_STATES, sanitize_element


class LmsScormSlide(models.Model):
    _name = 'lms.scorm.slide'
    _description = 'SCORM Authoring Slide'
    _order = 'course_id, sequence, id'

    course_id = fields.Many2one(
        'lms.scorm.course', string='Course', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='course_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Slide Title', required=True, default=lambda self: _('New Slide'),
                       translate=True)
    notes = fields.Text(
        string='Notes',
        help='Speaker notes or narration script. Authors and reviewers see them; learners do not.')
    hide_in_menu = fields.Boolean(string='Hide in Slide Menu')
    background_color = fields.Char(string='Background Colour')
    background_attachment_id = fields.Many2one(
        'ir.attachment', string='Background Picture', ondelete='set null')
    elements_json = fields.Text(string='Slide Content', default='[]')
    element_count = fields.Integer(compute='_compute_element_count', string='Items')

    # Gate: what the learner must do before Continue appears
    gate_require_interactions = fields.Boolean(
        string='Require Interactions', default=True,
        help='Continue only shows once every item marked "Required" on the slide has been '
             'used (videos watched, tabs opened, questions answered, ...).')
    gate_min_seconds = fields.Integer(
        string='Minimum Time (seconds)',
        help='Learners must stay on the slide at least this long before they can continue.')
    gate_pass_score = fields.Integer(
        string='Gate Pass Mark (%)',
        help='Learners must score at least this on the questions on this slide to continue. '
             '0 = no pass mark (answering is enough when the questions are required).')
    gate_max_attempts = fields.Integer(
        string='Gate Attempts',
        help='Attempts at the slide\'s questions before the learner is sent to the review '
             'slide. 0 = unlimited.')
    gate_fail_slide_id = fields.Many2one(
        'lms.scorm.slide', string='When Attempts Run Out, Go To',
        domain="[('course_id', '=', course_id), ('id', '!=', id)]", ondelete='set null',
        help='Slide to send the learner back to (e.g. to review the content) once the attempts '
             'are used up. They then retry the gate.')
    has_gate = fields.Boolean(compute='_compute_has_gate', string='Gated')
    comment_ids = fields.One2many('lms.scorm.comment', 'slide_id', string='Review Comments', copy=False)

    # Standard slides (Learning › Settings › Standard Slide Sets)
    standard_position = fields.Selection([
        ('start', 'At the start of every course'),
        ('end', 'At the end of every course'),
    ], string='Position in Courses', default='start',
        help='On a standard slide set: where this slide goes in the courses that use the set.')
    standard_set_id = fields.Many2one(
        'lms.scorm.slide.set', string='From Standard Set', readonly=True, ondelete='set null', index=True)
    standard_locked = fields.Boolean(string='Locked Standard Slide', readonly=True)
    open_comment_count = fields.Integer(compute='_compute_open_comment_count', string='Open Comments')

    _check_gate_pass_score = models.Constraint(
        'CHECK(gate_pass_score >= 0 AND gate_pass_score <= 100)',
        'The gate pass mark must be between 0 and 100.',
    )

    def _elements(self):
        self.ensure_one()
        try:
            data = json.loads(self.elements_json or '[]')
        except ValueError:
            return []
        return data if isinstance(data, list) else []

    @api.depends('elements_json')
    def _compute_element_count(self):
        for slide in self:
            slide.element_count = len(slide._elements())

    @api.depends('gate_require_interactions', 'gate_min_seconds', 'gate_pass_score', 'elements_json')
    def _compute_has_gate(self):
        for slide in self:
            slide.has_gate = bool(
                slide.gate_min_seconds or slide.gate_pass_score
                or (slide.gate_require_interactions and any(e.get('required') for e in slide._elements())))

    @api.depends('comment_ids.resolved', 'comment_ids.parent_id')
    def _compute_open_comment_count(self):
        for slide in self:
            slide.open_comment_count = len(slide.comment_ids.filtered(
                lambda c: not c.resolved and not c.parent_id))

    def _check_editable(self):
        if self.env.context.get('scorm_allow_locked_write'):
            return
        for slide in self:
            if slide.course_id.state not in EDITABLE_STATES:
                raise UserError(_(
                    '"%s" is no longer a draft, so its slides cannot be changed. '
                    'Create a new version to make changes.', slide.course_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        slides = super().create(vals_list)
        slides._check_editable()
        return slides

    def _check_standard_lock(self, vals=None):
        if self.env.context.get('scorm_standard_sync'):
            return
        if vals is not None and set(vals) <= {'sequence'}:
            return
        locked = self.filtered('standard_locked')
        if locked:
            raise UserError(_(
                '"%s" is a locked standard slide. Change it in Learning › Settings › SCORM '
                'Standard Slides, then update the course\'s standard slides.', locked[0].name))

    def write(self, vals):
        self._check_editable()
        self._check_standard_lock(vals)
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        self._check_standard_lock()
        return super().unlink()

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------
    def _editor_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'notes': self.notes or '',
            'hide_in_menu': self.hide_in_menu,
            'background_color': self.background_color or '',
            'background_attachment_id': self.background_attachment_id.id or False,
            'gate_require_interactions': self.gate_require_interactions,
            'gate_min_seconds': self.gate_min_seconds,
            'gate_pass_score': self.gate_pass_score,
            'gate_max_attempts': self.gate_max_attempts,
            'gate_fail_slide_id': self.gate_fail_slide_id.id or False,
            'standard_position': self.standard_position or 'start',
            'standard': bool(self.standard_set_id),
            'standard_locked': self.standard_locked,
            'elements': self._elements(),
        }

    @api.model
    def _editor_vals(self, data, sequence):
        elements = [e for e in (sanitize_element(e) for e in data.get('elements') or []) if e]

        def as_int(value, low=0, high=100000):
            try:
                return min(max(int(value or 0), low), high)
            except (TypeError, ValueError):
                return 0

        background = data.get('background_attachment_id')
        vals = {
            'sequence': sequence,
            'name': (data.get('name') or _('Slide %s', sequence))[:200],
            'notes': data.get('notes') or False,
            'hide_in_menu': bool(data.get('hide_in_menu')),
            'background_color': (data.get('background_color') or '')[:30] or False,
            'background_attachment_id': as_int(background) or False,
            'gate_require_interactions': bool(data.get('gate_require_interactions')),
            'gate_min_seconds': as_int(data.get('gate_min_seconds'), 0, 3600),
            'gate_pass_score': as_int(data.get('gate_pass_score'), 0, 100),
            'gate_max_attempts': as_int(data.get('gate_max_attempts'), 0, 100),
            'elements_json': json.dumps(elements),
        }
        if data.get('standard_position') in ('start', 'end'):
            vals['standard_position'] = data['standard_position']
        return vals

    def action_open_in_editor(self):
        self.ensure_one()
        action = self.course_id.action_open_editor()
        action['params']['slide_id'] = self.id
        return action
