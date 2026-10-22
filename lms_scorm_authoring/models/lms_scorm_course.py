import base64
import json
import mimetypes
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html_sanitize

from ..lib.package_builder import build_package

EDITABLE_STATES = ('draft',)
HTML_PROPS = ('html', 'front_html', 'back_html', 'pass_html', 'fail_html', 'popup_text', 'prompt',
              'feedback_correct', 'feedback_incorrect', 'label_html')
URL_PROPS = ('url',)
DEFAULT_LABELS = {
    'label_start': 'Start',
    'label_resume': 'Resume',
    'label_restart': 'Start Again',
    'label_next': 'Next',
    'label_back': 'Back',
    'label_continue': 'Continue',
    'label_submit': 'Submit',
    'label_retry': 'Try Again',
    'label_finish': 'Finish',
    'label_menu': 'Menu',
    'label_review': 'Review',
    'label_close': 'Close',
    'label_correct': 'Correct!',
    'label_incorrect': 'Not quite.',
    'label_locked': 'Complete the activities on this slide to continue',
    'label_wait': 'Continue in {seconds}s',
    'label_passed': 'Congratulations, you passed!',
    'label_failed': 'You did not reach the pass mark.',
    'label_score': 'Your score',
    'label_complete': 'You have completed this course. You can now close this window.',
}


def _label_field(key, string):
    return fields.Char(string=string, default=DEFAULT_LABELS[key], translate=True, required=True)


class LmsScormCourse(models.Model):
    _name = 'lms.scorm.course'
    _description = 'SCORM Authoring Course'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, version_number desc'

    name = fields.Char(string='Course Title', required=True, tracking=True, translate=True)
    description = fields.Text(
        string='Introduction', translate=True,
        help='Shown to learners on the start screen.')
    image = fields.Image(string='Thumbnail', max_width=512, max_height=512)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, tracking=True)

    # ── Versions ────────────────────────────────────────────────────────
    origin_id = fields.Many2one(
        'lms.scorm.course', string='Original Course', copy=False, index=True,
        ondelete='restrict', readonly=True,
        help='First version of this course; every version shares it.')
    previous_version_id = fields.Many2one(
        'lms.scorm.course', string='Previous Version', copy=False, readonly=True,
        ondelete='set null')
    version_number = fields.Integer(string='Version', default=1, copy=False, readonly=True)
    version_ids = fields.One2many(
        'lms.scorm.course', compute='_compute_version_ids', string='All Versions')
    version_count = fields.Integer(compute='_compute_version_ids')
    identifier = fields.Char(
        string='Package Identifier', copy=False, readonly=True,
        help='Stable SCORM identifier shared by every version of the course.')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'In Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('superseded', 'Superseded'),
    ], string='Status', default='draft', required=True, copy=False, tracking=True, index=True)
    published_date = fields.Datetime(string='Published On', copy=False, readonly=True)
    published_by_id = fields.Many2one('res.users', string='Published By', copy=False, readonly=True)

    # ── Approvals ───────────────────────────────────────────────────────
    approver_ids = fields.Many2many(
        'res.users', 'lms_scorm_course_approver_rel', 'course_id', 'user_id',
        string='Approvers',
        domain=lambda self: [('all_group_ids', 'in', self.env.ref(
            'lms_scorm_authoring.group_scorm_approve').ids)],
        help='Everyone listed must approve the course before it can be published. '
             'Leave empty to need one approval from any Approver.')
    approval_ids = fields.One2many('lms.scorm.approval', 'course_id', string='Approvals', copy=False)
    submitted_by_id = fields.Many2one('res.users', string='Submitted By', copy=False, readonly=True)
    submitted_date = fields.Datetime(string='Submitted On', copy=False, readonly=True)
    approval_round = fields.Integer(copy=False, default=0)
    can_approve = fields.Boolean(compute='_compute_can_approve')
    user_can_edit = fields.Boolean(compute='_compute_user_access')
    user_can_create = fields.Boolean(compute='_compute_user_access')

    # ── Content ─────────────────────────────────────────────────────────
    slide_ids = fields.One2many('lms.scorm.slide', 'course_id', string='Slides', copy=True)
    slide_count = fields.Integer(compute='_compute_slide_count')
    slide_width = fields.Integer(string='Slide Width (px)', default=1280, required=True)
    slide_height = fields.Integer(string='Slide Height (px)', default=720, required=True)
    comment_ids = fields.One2many('lms.scorm.comment', 'course_id', string='Review Comments', copy=False)
    open_comment_count = fields.Integer(compute='_compute_open_comment_count', string='Open Comments')

    # ── Delivery ────────────────────────────────────────────────────────
    scorm_version = fields.Selection([
        ('1.2', 'SCORM 1.2'),
        ('2004', 'SCORM 2004 (4th Edition)'),
    ], string='SCORM Version', default='1.2', required=True, tracking=True)
    navigation_mode = fields.Selection([
        ('linear', 'In order (locked)'),
        ('free', 'Free (any order)'),
    ], string='Navigation', default='linear', required=True,
        help='In order: learners must clear each slide before the next. '
             'Free: learners can jump to any slide from the menu (slide gates still apply '
             'to the Continue button).')
    allow_back = fields.Boolean(string='Allow Going Back', default=True)
    show_menu = fields.Boolean(string='Show Slide Menu', default=True)
    show_progress = fields.Boolean(string='Show Progress Bar', default=True)
    show_slide_numbers = fields.Boolean(string='Show Slide Numbers', default=True)
    show_start_screen = fields.Boolean(string='Show Start Screen', default=True)
    allow_resume = fields.Boolean(
        string='Resume Where Left Off', default=True,
        help='Learners return to the last slide they reached.')

    # ── Completion & assessment ─────────────────────────────────────────
    require_all_slides = fields.Boolean(
        string='Must View Every Slide', default=True,
        help='The course only completes once every slide has been viewed.')
    require_pass = fields.Boolean(
        string='Must Pass Assessment', default=False, tracking=True,
        help='Learners must reach the passing score on the scored questions.')
    passing_score = fields.Integer(string='Passing Score (%)', default=80, tracking=True)
    max_attempts = fields.Integer(
        string='Assessment Attempts', default=0,
        help='How many times the assessment can be taken. 0 = unlimited.')
    show_answers = fields.Boolean(
        string='Show Correct Answers', default=True,
        help='After the final attempt on a question, show the correct answer.')
    scored_question_count = fields.Integer(compute='_compute_slide_count', string='Scored Questions')

    # ── Branding ────────────────────────────────────────────────────────
    branding_source = fields.Selection([
        ('company', "Company's branding"),
        ('manual', 'Custom branding'),
    ], string='Branding', default='company', required=True)
    brand_logo = fields.Image(string='Logo', max_width=600, max_height=200)
    brand_primary_color = fields.Char(string='Primary Colour', default='#1f6feb')
    brand_secondary_color = fields.Char(string='Secondary Colour', default='#0b3d91')
    brand_background_color = fields.Char(string='Page Background', default='#f4f6f8')
    brand_slide_color = fields.Char(string='Slide Background', default='#ffffff')
    brand_text_color = fields.Char(string='Text Colour', default='#1f2933')
    brand_button_text_color = fields.Char(string='Button Text Colour', default='#ffffff')
    brand_font_id = fields.Many2one(
        'lms.scorm.font', string='Font', ondelete='set null',
        default=lambda self: self.env.ref('lms_scorm_authoring.font_open_sans', raise_if_not_found=False))
    effective_logo = fields.Image(compute='_compute_effective_branding', string='Logo in Use')
    effective_primary_color = fields.Char(compute='_compute_effective_branding', string='Primary')
    effective_secondary_color = fields.Char(compute='_compute_effective_branding', string='Secondary')
    effective_font_id = fields.Many2one(
        'lms.scorm.font', compute='_compute_effective_branding', string='Font in Use')

    # ── Learner button labels ───────────────────────────────────────────
    label_start = _label_field('label_start', 'Start')
    label_resume = _label_field('label_resume', 'Resume')
    label_restart = _label_field('label_restart', 'Start Again')
    label_next = _label_field('label_next', 'Next')
    label_back = _label_field('label_back', 'Back')
    label_continue = _label_field('label_continue', 'Continue')
    label_submit = _label_field('label_submit', 'Submit Answer')
    label_retry = _label_field('label_retry', 'Try Again')
    label_finish = _label_field('label_finish', 'Finish')
    label_menu = _label_field('label_menu', 'Menu')
    label_review = _label_field('label_review', 'Review')
    label_close = _label_field('label_close', 'Close')
    label_correct = _label_field('label_correct', 'Correct Feedback')
    label_incorrect = _label_field('label_incorrect', 'Incorrect Feedback')
    label_locked = _label_field('label_locked', 'Locked Message')
    label_wait = _label_field('label_wait', 'Minimum Time Message')
    label_passed = _label_field('label_passed', 'Passed Message')
    label_failed = _label_field('label_failed', 'Failed Message')
    label_score = _label_field('label_score', 'Score Label')
    label_complete = _label_field('label_complete', 'Completed Message')

    # ── LMS ─────────────────────────────────────────────────────────────
    lms_course_ids = fields.One2many(
        'lms.course', 'scorm_course_id', string='LMS Courses',
        groups='learning_management.group_lms_employee')
    lms_course_count = fields.Integer(compute='_compute_lms_course_count')

    _check_passing_score = models.Constraint(
        'CHECK(passing_score >= 0 AND passing_score <= 100)',
        'The passing score must be between 0 and 100.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    def _compute_version_ids(self):
        for course in self:
            root = course.origin_id or course
            if not root.id:
                course.version_ids = course
                course.version_count = 1
                continue
            versions = self.with_context(active_test=False).search(
                ['|', ('id', '=', root.id), ('origin_id', '=', root.id)])
            course.version_ids = versions
            course.version_count = len(versions)

    @api.depends('slide_ids', 'slide_ids.elements_json')
    def _compute_slide_count(self):
        for course in self:
            course.slide_count = len(course.slide_ids)
            course.scored_question_count = sum(
                1 for slide in course.slide_ids for el in slide._elements()
                if el.get('scored') and el.get('type') in QUESTION_TYPES)

    @api.depends('comment_ids.resolved')
    def _compute_open_comment_count(self):
        for course in self:
            course.open_comment_count = len(course.comment_ids.filtered(
                lambda c: not c.resolved and not c.parent_id))

    def _compute_lms_course_count(self):
        LmsCourse = self.env['lms.course'].sudo().with_context(active_test=False)
        for course in self:
            course.lms_course_count = LmsCourse.search_count(
                [('scorm_course_id', 'in', course.version_ids.ids)]) if course.id else 0

    @api.depends('branding_source', 'company_id', 'brand_logo', 'brand_primary_color',
                 'brand_secondary_color', 'brand_font_id')
    def _compute_effective_branding(self):
        for course in self:
            brand = course._get_branding()
            course.effective_logo = brand['logo']
            course.effective_primary_color = brand['primary_color']
            course.effective_secondary_color = brand['secondary_color']
            course.effective_font_id = brand['font']

    @api.depends_context('uid')
    def _compute_user_access(self):
        # Creating is opened by record rules, so the ACL alone can't tell
        user = self.env.user
        can_create = any(user.has_group('lms_scorm_authoring.group_scorm_course_%s' % code)
                         for code in ('create_only', 'edit_own', 'edit_team', 'edit_all'))
        for course in self:
            course.user_can_edit = not course.id or course.has_access('write')
            course.user_can_create = can_create

    @api.depends('state', 'approval_ids.state', 'approval_ids.user_id', 'submitted_by_id')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        for course in self:
            course.can_approve = course.state == 'review' and bool(course._my_pending_approvals())

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('identifier'):
                vals['identifier'] = 'cc_scorm_%s' % self.env['ir.sequence'].sudo().next_by_code(
                    'lms.scorm.course.identifier')
        return super().create(vals_list)

    def write(self, vals):
        locked = set(vals) & self._content_fields()
        if locked and not self.env.context.get('scorm_allow_locked_write'):
            for course in self:
                if course.state not in EDITABLE_STATES:
                    raise UserError(_(
                        '"%(name)s" is %(state)s, so its content can no longer be changed. '
                        'Create a new version to make changes.',
                        name=course.display_name,
                        state=dict(course._fields['state'].selection)[course.state].lower()))
        return super().write(vals)

    def unlink(self):
        for course in self:
            if course.state in ('published', 'superseded') and course.lms_course_ids:
                raise UserError(_(
                    '"%s" is used by LMS courses and cannot be deleted. Archive it instead.',
                    course.display_name))
        return super().unlink()

    @api.model
    def _content_fields(self):
        """Fields that only change while a version is a draft."""
        ignore = {
            'state', 'active', 'approval_ids', 'approver_ids', 'submitted_by_id', 'submitted_date',
            'approval_round', 'published_date', 'published_by_id', 'comment_ids', 'lms_course_ids',
            'message_follower_ids', 'activity_ids', 'message_ids', 'origin_id',
            'previous_version_id', 'version_number', 'identifier', 'company_id', 'image',
        }
        return {
            name for name, field in self._fields.items()
            if field.store and not name.startswith(('org_', 'message_', 'activity_', 'website_'))
            and name not in models.MAGIC_COLUMNS and name not in ignore
        }

    @api.depends('name', 'version_number')
    def _compute_display_name(self):
        for course in self:
            course.display_name = '%s (v%d)' % (course.name or _('New Course'), course.version_number or 1)

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------
    def _get_branding(self):
        """Branding in effect: the company's when chosen, else the course's own."""
        self.ensure_one()
        font = self.brand_font_id
        use_company = self.branding_source == 'company' or self.env.context.get(
            'scorm_force_company_branding')
        if use_company and self.company_id:
            company = self.company_id
            primary = getattr(company, 'primary_color', False) or self.brand_primary_color
            secondary = getattr(company, 'secondary_color', False) or self.brand_secondary_color
            company_font = self.env['lms.scorm.font']._match_company_font(getattr(company, 'font', False))
            return {
                'logo': company.logo or self.brand_logo,
                'primary_color': primary,
                'secondary_color': secondary,
                'background_color': self.brand_background_color,
                'slide_color': self.brand_slide_color,
                'text_color': self.brand_text_color,
                'button_text_color': self.brand_button_text_color,
                'font': company_font or font,
            }
        return {
            'logo': self.brand_logo,
            'primary_color': self.brand_primary_color,
            'secondary_color': self.brand_secondary_color,
            'background_color': self.brand_background_color,
            'slide_color': self.brand_slide_color,
            'text_color': self.brand_text_color,
            'button_text_color': self.brand_button_text_color,
            'font': font,
        }

    def action_copy_company_branding(self):
        """Switch to custom branding, starting from the company's."""
        for course in self:
            brand = course.with_context(scorm_force_company_branding=True)._get_branding()
            course.write({
                'branding_source': 'manual',
                'brand_logo': brand['logo'],
                'brand_primary_color': brand['primary_color'],
                'brand_secondary_color': brand['secondary_color'],
                'brand_font_id': brand['font'].id,
            })

    def action_reset_labels(self):
        self.write(dict(DEFAULT_LABELS))

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------
    def _check_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            group = self.env.ref(xmlid)
            raise AccessError(_('You need the "%s" permission to do this.',
                                group.privilege_id.name or group.name))

    def action_new_version(self):
        """Copy this version (slides, settings, branding) into a new draft version."""
        self.ensure_one()
        self.check_access('read')
        self.check_access('create')
        root = self.origin_id or self
        family = self.with_context(active_test=False).search(
            ['|', ('id', '=', root.id), ('origin_id', '=', root.id)])
        open_draft = family.filtered(lambda c: c.state in ('draft', 'review', 'approved'))
        if open_draft:
            raise UserError(_(
                '%s is already being worked on. Finish, publish or delete it before starting '
                'another version.', open_draft[0].display_name))
        new = self.copy({
            'origin_id': root.id,
            'previous_version_id': self.id,
            'version_number': max(family.mapped('version_number')) + 1,
            'identifier': self.identifier,
            'name': self.name,
            'approver_ids': [(6, 0, self.approver_ids.ids)],
        })
        new._remap_copied_slide_links(self)
        new.message_post(body=_('Version %(new)s created from version %(old)s.',
                                new=new.version_number, old=self.version_number))
        return new.action_open_form()

    def _remap_copied_slide_links(self, source):
        """Point 'go to slide' actions at the copied slides instead of the source's."""
        mapping = {str(old.id): new.id for old, new in zip(source.slide_ids, self.slide_ids)}
        for slide in self.slide_ids:
            elements = slide._elements()
            changed = False
            for el in elements:
                target = el.get('props', {}).get('target_slide')
                if target and str(target) in mapping:
                    el['props']['target_slide'] = mapping[str(target)]
                    changed = True
            if slide.gate_fail_slide_id and str(slide.gate_fail_slide_id.id) in mapping:
                slide.gate_fail_slide_id = mapping[str(slide.gate_fail_slide_id.id)]
            if changed:
                slide.elements_json = json.dumps(elements)

    def action_view_versions(self):
        self.ensure_one()
        return {
            'name': _('Versions of %s', self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.course',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.version_ids.ids)],
            'context': {'active_test': False, 'create': False},
        }

    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.course',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------
    def _approvers_for_round(self):
        self.ensure_one()
        group = self.env.ref('lms_scorm_authoring.group_scorm_approve')
        return self.approver_ids.filtered(lambda u: u.active and group in u.all_group_ids)

    def _my_pending_approvals(self):
        self.ensure_one()
        user = self.env.user
        if self.state != 'review' or not user.has_group('lms_scorm_authoring.group_scorm_approve'):
            return self.env['lms.scorm.approval']
        is_admin = user.has_group('lms_scorm_authoring.group_scorm_admin')
        if self.submitted_by_id == user and not is_admin:
            return self.env['lms.scorm.approval']
        pending = self.approval_ids.filtered(
            lambda a: a.state == 'pending' and a.round == self.approval_round)
        mine = pending.filtered(lambda a: a.user_id == user)
        if mine:
            return mine
        anyone = pending.filtered(lambda a: not a.user_id)
        if anyone:
            return anyone[:1]
        if is_admin:
            return pending
        return self.env['lms.scorm.approval']

    def _check_ready_for_review(self):
        self.ensure_one()
        if not self.slide_ids:
            raise UserError(_('Add at least one slide before submitting the course.'))
        if self.require_pass and not self.scored_question_count:
            raise UserError(_(
                '"Must Pass Assessment" is on but the course has no scored questions. '
                'Mark at least one question as scored, or turn the setting off.'))
        for slide in self.slide_ids:
            if slide.gate_pass_score and not any(
                    el.get('type') in QUESTION_TYPES and el.get('type') != 'survey'
                    for el in slide._elements()):
                raise UserError(_(
                    'Slide "%s" needs a pass score but has no questions to answer.', slide.name))

    def action_submit_review(self):
        for course in self:
            course.check_access('write')
            if course.state != 'draft':
                raise UserError(_('Only draft courses can be submitted for approval.'))
            course._check_ready_for_review()
            approvers = course._approvers_for_round()
            round_no = course.approval_round + 1
            lines = [(0, 0, {'user_id': user.id, 'round': round_no}) for user in approvers]
            if not lines:
                lines = [(0, 0, {'user_id': False, 'round': round_no})]
            course.sudo().write({
                'state': 'review',
                'approval_round': round_no,
                'submitted_by_id': self.env.uid,
                'submitted_date': fields.Datetime.now(),
                'approval_ids': lines,
            })
            notify = approvers or self.env.ref(
                'lms_scorm_authoring.group_scorm_approve').sudo().all_user_ids.filtered(
                    lambda u: u != self.env.user and u.company_ids & course.company_id)
            for user in notify:
                course.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', user_id=user.id,
                    summary=_('Review SCORM course %s', course.display_name),
                    note=_('Please review the course and approve it or request changes.'))
            course.message_post(body=_('Submitted for approval.'))
        return True

    def action_withdraw_review(self):
        for course in self:
            if course.state != 'review':
                continue
            if course.submitted_by_id != self.env.user:
                course._check_group('lms_scorm_authoring.group_scorm_approve')
            course = course.sudo()
            course.approval_ids.filtered(lambda a: a.state == 'pending').write({'state': 'cancelled'})
            course.activity_unlink(['mail.mail_activity_data_todo'])
            course.state = 'draft'
            course.message_post(body=_('Withdrawn from review.'))
        return True

    def action_approve(self, note=False):
        self.ensure_one()
        self._check_group('lms_scorm_authoring.group_scorm_approve')
        lines = self._my_pending_approvals().sudo()
        if not lines:
            if self.submitted_by_id == self.env.user:
                raise UserError(_('You cannot approve a course you submitted yourself.'))
            raise UserError(_('There is no approval waiting for you on this course.'))
        for line in lines:
            line.write({
                'state': 'approved', 'user_id': line.user_id.id or self.env.uid,
                'decided_by_id': self.env.uid,
                'decision_date': fields.Datetime.now(), 'note': note or False,
            })
        course = self.sudo()
        course.activity_feedback(['mail.mail_activity_data_todo'], user_id=self.env.uid,
                                 feedback=_('Approved'))
        course.message_post(body=_('Approved by %(user)s.%(note)s', user=self.env.user.name,
                                 note=(' ' + note) if note else ''))
        pending = course.approval_ids.filtered(
            lambda a: a.state == 'pending' and a.round == course.approval_round)
        if not pending:
            course.activity_unlink(['mail.mail_activity_data_todo'])
            course.state = 'approved'
            if course.submitted_by_id:
                course.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=course.submitted_by_id.id,
                    summary=_('%s is approved and ready to publish', course.display_name))
        return True

    def action_reject(self, note):
        self.ensure_one()
        self._check_group('lms_scorm_authoring.group_scorm_approve')
        if not note:
            raise UserError(_('Say what needs to change so the author can fix it.'))
        lines = self._my_pending_approvals().sudo()
        if not lines:
            raise UserError(_('There is no approval waiting for you on this course.'))
        course = self.sudo()
        lines[:1].write({
            'state': 'rejected', 'user_id': lines[:1].user_id.id or self.env.uid,
            'decided_by_id': self.env.uid,
            'decision_date': fields.Datetime.now(), 'note': note,
        })
        course.approval_ids.filtered(lambda a: a.state == 'pending').write({'state': 'cancelled'})
        course.activity_unlink(['mail.mail_activity_data_todo'])
        course.state = 'draft'
        course.message_post(body=_('Changes requested by %(user)s: %(note)s',
                                   user=self.env.user.name, note=note))
        if course.submitted_by_id:
            course.activity_schedule(
                'mail.mail_activity_data_todo', user_id=course.submitted_by_id.id,
                summary=_('Changes requested on %s', course.display_name), note=note)
        return True

    def action_open_decision_wizard(self):
        self.ensure_one()
        return {
            'name': _('Approve or Request Changes'),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_course_id': self.id},
        }

    def action_publish(self):
        """Make an approved version the live one for learners."""
        self._check_group('lms_scorm_authoring.group_scorm_approve')
        for course in self.sudo():
            if course.state != 'approved':
                raise UserError(_('Only approved courses can be published.'))
            root = course.origin_id or course
            family = course.with_context(active_test=False).search(
                ['|', ('id', '=', root.id), ('origin_id', '=', root.id), ('id', '!=', course.id)])
            previous = family.filtered(lambda c: c.state == 'published')
            previous.write({'state': 'superseded'})
            course.write({
                'state': 'published',
                'published_date': fields.Datetime.now(),
                'published_by_id': self.env.uid,
            })
            course.activity_unlink(['mail.mail_activity_data_todo'])
            # LMS courses using any version of this course move to the new one
            lms_courses = self.env['lms.course'].sudo().with_context(active_test=False).search(
                [('scorm_course_id', 'in', (family | course).ids)])
            if lms_courses:
                lms_courses.write({'scorm_course_id': course.id})
            course.message_post(body=_(
                'Published version %(version)s.%(lms)s', version=course.version_number,
                lms=_(' Updated %s LMS course(s).', len(lms_courses)) if lms_courses else ''))
        return True

    # ------------------------------------------------------------------
    # Package
    # ------------------------------------------------------------------
    def _package_filename(self):
        self.ensure_one()
        slug = re.sub(r'[^A-Za-z0-9]+', '_', self.name or 'course').strip('_')[:60] or 'course'
        suffix = '' if self.state == 'published' else '_%s' % self.state
        return '%s_v%d%s_scorm%s.zip' % (
            slug, self.version_number, suffix, self.scorm_version.replace('.', ''))

    def _build_package(self, preview=False):
        """Return the SCORM .zip for this version as bytes."""
        self.ensure_one()
        course = self.sudo()
        assets = {}

        def asset_path(attachment_id):
            if not attachment_id:
                return ''
            try:
                attachment_id = int(attachment_id)
            except (TypeError, ValueError):
                return ''
            if attachment_id not in assets:
                attachment = self.env['ir.attachment'].sudo().browse(attachment_id).exists()
                if not attachment or attachment.res_model != 'lms.scorm.course':
                    assets[attachment_id] = None
                else:
                    ext = mimetypes.guess_extension(attachment.mimetype or '') or ''
                    if ext == '.jpe':
                        ext = '.jpg'
                    assets[attachment_id] = ('assets/a%d%s' % (attachment.id, ext), attachment.raw)
            return assets[attachment_id][0] if assets[attachment_id] else ''

        brand = course._get_branding()
        logo_path = ''
        files = {}
        if brand['logo']:
            logo_data = base64.b64decode(brand['logo'])
            logo_path = 'assets/logo.%s' % ('svg' if logo_data[:5] in (b'<?xml', b'<svg ') else 'png')
            files[logo_path] = logo_data

        slides = []
        index_by_id = {}
        for index, slide in enumerate(course.slide_ids):
            index_by_id[slide.id] = index
        for slide in course.slide_ids:
            elements = []
            for el in slide._elements():
                el = json.loads(json.dumps(el))
                props = el.setdefault('props', {})
                for key in ('attachment_id', 'poster_attachment_id'):
                    if props.get(key):
                        props[key.replace('attachment_id', 'src')] = asset_path(props.pop(key))
                    else:
                        props.pop(key, None)
                target = props.get('target_slide')
                if target:
                    try:
                        props['target_slide'] = index_by_id.get(int(target), -1)
                    except (TypeError, ValueError):
                        props['target_slide'] = -1
                el.pop('comments', None)
                elements.append(el)
            slides.append({
                'id': slide.id,
                'title': slide.name or '',
                'hide_in_menu': slide.hide_in_menu,
                'background_color': slide.background_color or '',
                'background_image': asset_path(slide.background_attachment_id.id),
                'gate': {
                    'require_interactions': slide.gate_require_interactions,
                    'min_seconds': slide.gate_min_seconds,
                    'pass_score': slide.gate_pass_score,
                    'max_attempts': slide.gate_max_attempts,
                    'fail_slide': index_by_id.get(slide.gate_fail_slide_id.id, -1)
                    if slide.gate_fail_slide_id else -1,
                },
                'elements': elements,
            })
        for asset in assets.values():
            if asset:
                files[asset[0]] = asset[1]

        font = brand['font']
        data = {
            'identifier': course.identifier or 'cc_scorm_%d' % course.id,
            'title': course.name,
            'description': course.description or '',
            'version': course.version_number,
            'scorm_version': course.scorm_version,
            'width': course.slide_width,
            'height': course.slide_height,
            'preview': bool(preview),
            'settings': {
                'navigation': course.navigation_mode,
                'allow_back': course.allow_back,
                'show_menu': course.show_menu,
                'show_progress': course.show_progress,
                'show_slide_numbers': course.show_slide_numbers,
                'show_start_screen': course.show_start_screen,
                'allow_resume': course.allow_resume,
                'require_all_slides': course.require_all_slides,
                'require_pass': course.require_pass,
                'passing_score': course.passing_score,
                'max_attempts': course.max_attempts,
                'show_answers': course.show_answers,
            },
            'branding': {
                'logo': logo_path,
                'primary_color': brand['primary_color'] or '#1f6feb',
                'secondary_color': brand['secondary_color'] or '#0b3d91',
                'background_color': brand['background_color'] or '#f4f6f8',
                'slide_color': brand['slide_color'] or '#ffffff',
                'text_color': brand['text_color'] or '#1f2933',
                'button_text_color': brand['button_text_color'] or '#ffffff',
                'font_family': font.css_family if font else 'Arial, Helvetica, sans-serif',
                'font_url': font._google_font_url() if font else '',
            },
            'labels': {key: course[key] or default for key, default in DEFAULT_LABELS.items()},
            'slides': slides,
        }
        return build_package(data, files)

    def action_download_package(self):
        self.ensure_one()
        if self.state not in ('approved', 'published', 'superseded'):
            raise UserError(_(
                'Only approved or published versions can be downloaded. Use Preview to try a draft.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/scorm_authoring/%d/download' % self.id,
            'target': 'self',
        }

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/scorm_authoring/%d/preview/index.html' % self.id,
            'target': 'new',
        }

    def action_open_editor(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'lms_scorm_authoring.editor',
            'name': _('Edit %s', self.display_name),
            'params': {'course_id': self.id},
            # Kept in the URL, so reloading the page reopens this course
            'context': {'active_id': self.id, 'active_model': 'lms.scorm.course'},
        }

    def action_import_presentation(self):
        self.ensure_one()
        return {
            'name': _('Import Presentation'),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_course_id': self.id},
        }

    def action_view_lms_courses(self):
        self.ensure_one()
        return {
            'name': _('LMS Courses'),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.course',
            'view_mode': 'list,form',
            'domain': [('scorm_course_id', 'in', self.version_ids.ids)],
            'context': {'default_scorm_course_id': self.id, 'default_delivery_mode': 'scorm',
                        'default_course_type': 'elearning'},
        }

    def action_view_comments(self):
        self.ensure_one()
        return {
            'name': _('Review Comments'),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.scorm.comment',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {'search_default_open': 1, 'create': False},
        }

    # ------------------------------------------------------------------
    # Editor API
    # ------------------------------------------------------------------
    def _editor_permissions(self):
        self.ensure_one()
        user = self.env.user
        can_write = self.has_access('write')
        reviewer = user.has_group('lms_scorm_authoring.group_scorm_review') or user.has_group(
            'lms_scorm_authoring.group_scorm_approve')
        return {
            'can_edit': can_write and self.state in EDITABLE_STATES,
            'can_comment': can_write or reviewer,
            'can_resolve': can_write or reviewer,
        }


    def editor_load(self):
        self.ensure_one()
        self.check_access('read')
        brand = self._get_branding()
        state_labels = dict(self._fields['state'].selection)
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'state': self.state,
            'state_label': state_labels.get(self.state),
            'width': self.slide_width,
            'height': self.slide_height,
            'permissions': self._editor_permissions(),
            # Only whether a key is set: the keys never leave the server
            'ai_available': bool(self._ai_providers()),
            'ai_provider': (self._ai_providers() or [(None, '', None)])[0][1],
            'branding': {
                'primary_color': brand['primary_color'] or '#1f6feb',
                'secondary_color': brand['secondary_color'] or '#0b3d91',
                'slide_color': brand['slide_color'] or '#ffffff',
                'text_color': brand['text_color'] or '#1f2933',
                'button_text_color': brand['button_text_color'] or '#ffffff',
                'font_family': brand['font'].css_family if brand['font'] else 'Arial, Helvetica, sans-serif',
                'font_url': brand['font']._google_font_url() if brand['font'] else '',
            },
            'labels': {'submit': self.label_submit},
            'slides': [slide._editor_data() for slide in self.slide_ids],
            'comments': [c._editor_data() for c in self.comment_ids.sorted('create_date')],
        }

    def editor_save(self, payload):
        """Save the editor's slides. ``payload``: {'slides': [...], 'deleted': [ids]}."""
        self.ensure_one()
        self.check_access('write')
        if not self._editor_permissions()['can_edit']:
            raise UserError(_('This version can no longer be edited. Create a new version to make changes.'))
        Slide = self.env['lms.scorm.slide']
        deleted = [int(i) for i in payload.get('deleted') or [] if str(i).isdigit()]
        if deleted:
            Slide.search([('id', 'in', deleted), ('course_id', '=', self.id)]).unlink()
        key_map = {}
        saved = Slide
        for sequence, data in enumerate(payload.get('slides') or [], start=1):
            vals = Slide._editor_vals(data, sequence)
            key = data.get('id')
            slide = Slide.browse(int(key)) if isinstance(key, int) or str(key).isdigit() else Slide
            if slide and slide.exists() and slide.course_id == self:
                slide.write(vals)
            else:
                vals['course_id'] = self.id
                slide = Slide.create(vals)
            key_map[str(key)] = slide.id
            saved |= slide
        # Point references to new slides at their real ids
        for slide in saved:
            elements = slide._elements()
            changed = False
            for el in elements:
                target = el.get('props', {}).get('target_slide')
                if target and str(target) in key_map and key_map[str(target)] != target:
                    el['props']['target_slide'] = key_map[str(target)]
                    changed = True
            if changed:
                slide.elements_json = json.dumps(elements)
        for data in payload.get('slides') or []:
            fail_key = data.get('gate_fail_slide_id')
            slide = Slide.browse(key_map.get(str(data.get('id'))))
            if fail_key and str(fail_key) in key_map:
                slide.gate_fail_slide_id = key_map[str(fail_key)]
            elif not fail_key and slide.gate_fail_slide_id:
                slide.gate_fail_slide_id = False
        return {'key_map': key_map, 'slides': [s._editor_data() for s in self.slide_ids]}

    def editor_upload_asset(self, name, data_b64, mimetype=False):
        """Store an uploaded picture/video/audio for this course; returns {id, url}."""
        self.ensure_one()
        self.check_access('write')
        if not self._editor_permissions()['can_edit']:
            raise UserError(_('This version can no longer be edited.'))
        mimetype = mimetype or mimetypes.guess_type(name or '')[0] or 'application/octet-stream'
        if not mimetype.startswith(('image/', 'video/', 'audio/')):
            raise UserError(_('Only pictures, video and audio files can be added.'))
        attachment = self.env['ir.attachment'].create({
            'name': name or 'asset',
            'datas': data_b64,
            'mimetype': mimetype,
            'res_model': 'lms.scorm.course',
            'res_id': self.id,
        })
        return {'id': attachment.id, 'url': '/web/content/%d' % attachment.id,
                'mimetype': attachment.mimetype, 'name': attachment.name}

    def editor_add_comment(self, slide_id, body, element_id=False, pos_x=0, pos_y=0, parent_id=False):
        self.ensure_one()
        if not self._editor_permissions()['can_comment']:
            raise AccessError(_('You cannot comment on this course.'))
        slide = self.env['lms.scorm.slide'].browse(int(slide_id))
        if slide.course_id != self:
            raise UserError(_('Save the slide before commenting on it.'))
        comment = self.env['lms.scorm.comment'].sudo().create({
            'slide_id': slide.id,
            'body': body,
            'element_id': element_id or False,
            'pos_x': pos_x or 0,
            'pos_y': pos_y or 0,
            'parent_id': parent_id or False,
            'author_id': self.env.uid,
        })
        return comment._editor_data()

    def editor_resolve_comment(self, comment_id, resolved=True):
        self.ensure_one()
        if not self._editor_permissions()['can_resolve']:
            raise AccessError(_('You cannot resolve comments on this course.'))
        comment = self.env['lms.scorm.comment'].sudo().browse(int(comment_id))
        if comment.course_id != self:
            raise UserError(_('This comment belongs to another course.'))
        comment._set_resolved(resolved)
        return comment._editor_data()


QUESTION_TYPES = ('mcq', 'mrq', 'truefalse', 'fillblank', 'matching', 'sequence', 'survey')


def sanitize_element(element):
    """Clean one element dict from the editor or the importer before storing it."""
    if not isinstance(element, dict):
        return None
    clean = {
        'id': str(element.get('id') or '')[:40] or None,
        'type': str(element.get('type') or '')[:30],
    }
    if not clean['id'] or not clean['type']:
        return None
    for key in ('x', 'y', 'w', 'h', 'z', 'rotation'):
        try:
            clean[key] = round(float(element.get(key) or 0))
        except (TypeError, ValueError):
            clean[key] = 0
    clean['required'] = bool(element.get('required'))
    clean['scored'] = bool(element.get('scored'))
    if element.get('hidden'):
        clean['hidden'] = True
    style = element.get('style') if isinstance(element.get('style'), dict) else {}
    clean['style'] = {k: v for k, v in style.items()
                      if isinstance(v, (str, int, float, bool)) and len(str(v)) < 300
                      and not re.search(r'url\s*\(|expression\s*\(|javascript:', str(v), re.I)}
    props = element.get('props') if isinstance(element.get('props'), dict) else {}
    clean['props'] = _sanitize_value(props)
    return clean


def _sanitize_value(value, key=None):
    if isinstance(value, dict):
        return {str(k)[:60]: _sanitize_value(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v, key) for v in value[:500]]
    if isinstance(value, str):
        if key in HTML_PROPS or (key == 'text' and '<' in value):
            return html_sanitize(value, sanitize_form=True, strip_classes=False) or ''
        if key in URL_PROPS and value and not value.lower().startswith(('http://', 'https://', 'mailto:')):
            return ''
        return value[:20000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2000]
