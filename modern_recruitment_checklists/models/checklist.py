# -*- coding: utf-8 -*-
import base64
import hmac
import logging
import uuid
from datetime import datetime

import pytz
from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools import email_normalize

from odoo.addons.checklists.models.checklist_question_condition import MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES
from odoo.addons.checklists.models.checklist_template import LAYOUT_TYPES

_logger = logging.getLogger(__name__)

# Answer types the online questionnaire can't offer (they pick records of
# this database, which applicants must not browse).
PUBLIC_SKIPPED_TYPES = ('many2one', 'many2many')
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class Checklist(models.Model):
    _inherit = 'checklist.checklist'

    talent_applicant_id = fields.Many2one(
        'hr.applicant', string='Applicant', index='btree_not_null', ondelete='set null', tracking=True,
    )
    talent_job_id = fields.Many2one(
        'hr.job', string='Job Position', index='btree_not_null', ondelete='set null', tracking=True,
        help='The job position the applicant applied for, set when they submit the questionnaire.',
    )
    talent_access_token = fields.Char(copy=False, groups='base.group_system')
    talent_submitted_date = fields.Datetime(string='Submitted by Applicant', readonly=True, copy=False)
    talent_url = fields.Char(string='Questionnaire Link', compute='_compute_talent_url')

    @api.depends('talent_applicant_id')
    def _compute_talent_url(self):
        for checklist in self:
            token = checklist.sudo().talent_access_token
            checklist.talent_url = token and '%s/talent/questionnaire/%s/%s' % (
                checklist.get_base_url(), checklist.id, token)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('talent_applicant_id') and not vals.get('talent_access_token'):
                vals['talent_access_token'] = uuid.uuid4().hex
        return super().create(vals_list)

    def _talent_check_token(self, token):
        self.ensure_one()
        stored = self.sudo().talent_access_token
        return bool(stored and token and hmac.compare_digest(stored, token))

    # ── Online questionnaire ─────────────────────────────────────────────

    def _talent_tz(self):
        """The time zone date-times on the questionnaire are typed in."""
        self.ensure_one()
        name = self.talent_applicant_id.user_id.tz or self.create_uid.tz or 'UTC'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _talent_public_lines(self):
        """The lines the online questionnaire shows, in order."""
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.question_type not in PUBLIC_SKIPPED_TYPES)

    def _talent_apply_answers(self, form, files):
        """Store the answers posted by the online questionnaire (sudo)."""
        self.ensure_one()
        for line in self._talent_public_lines():
            kind = line.question_type
            if kind in LAYOUT_TYPES:
                continue
            key = 'line_%s' % line.id
            vals = line._talent_answer_vals(kind, key, form, files)
            if vals:
                line.write(vals)

    def _talent_submit(self):
        """The applicant submitted: complete it, link it to the job they
        applied for and tell the recruiter."""
        self.ensure_one()
        applicant = self.talent_applicant_id
        self.write({
            'state': 'done',
            'talent_submitted_date': fields.Datetime.now(),
            'talent_job_id': applicant.job_id.id or self.talent_job_id.id,
        })
        link = self._get_html_link(title=self.template_id.name)
        if applicant:
            recipients = (applicant.user_id | self.create_uid).filtered(lambda u: not u._is_public())
            applicant.message_post(
                body=Markup(self.env._('%(name)s completed the questionnaire %(link)s.')) % {
                    'name': applicant.partner_name or self.env._('The applicant'), 'link': link},
                partner_ids=recipients.partner_id.ids,
                author_id=applicant.partner_id.id or None,
                subtype_xmlid='mail.mt_note',
            )
        if self.talent_job_id:
            self.talent_job_id.message_post(
                body=Markup(self.env._('%(name)s completed the questionnaire %(link)s.')) % {
                    'name': applicant.partner_name or self.env._('An applicant'), 'link': link},
                author_id=applicant.partner_id.id or None,
                subtype_xmlid='mail.mt_note',
            )


class ChecklistLine(models.Model):
    _inherit = 'checklist.line'

    def _talent_options(self):
        self.ensure_one()
        return self.question_id.option_ids.filtered('active') if self.question_id else self.env[
            'checklist.question.option']

    def _talent_answer_vals(self, kind, key, form, files):
        """The line's values from the posted form, or {} to leave it as it is."""
        self.ensure_one()
        value = (form.get(key) or '').strip()
        if kind == 'text':
            return {'value_text': value or False}
        if kind == 'text_area':
            return {'value_text_area': form.get(key) or False}
        if kind == 'phone':
            return {'value_phone': value or False}
        if kind == 'email':
            return {'value_email': (email_normalize(value) or value) if value else False}
        if kind == 'website':
            return {'value_url': value or False}
        if kind in ('number', 'integer'):
            try:
                number = float(value.replace(',', '')) if value else 0.0
            except ValueError:
                return {}
            return {'value_number': number} if kind == 'number' else {'value_integer': int(number)}
        if kind == 'date':
            try:
                return {'value_date': datetime.strptime(value, '%d/%m/%Y').date() if value else False}
            except ValueError:
                return {}
        if kind == 'datetime':
            if not value:
                return {'value_datetime': False}
            try:
                local = datetime.strptime(value, '%d/%m/%Y %H:%M')
            except ValueError:
                return {}
            return {'value_datetime': self._talent_to_utc(local)}
        if kind == 'boolean':
            # A hidden "0" always comes first; the ticked switch adds "1".
            return {'value_boolean': '1' in form.getlist(key)}
        if kind in SINGLE_OPTION_TYPES:
            option = self._talent_options().filtered(lambda o: str(o.id) == value)
            return {'value_option_id': option.id or False}
        if kind in MULTI_OPTION_TYPES:
            wanted = set(form.getlist(key))
            options = self._talent_options().filtered(lambda o: str(o.id) in wanted)
            return {'value_option_ids': [fields.Command.set(options.ids)]}
        if kind == 'geolocation':
            try:
                latitude = float(form.get(key + '_lat') or 0)
                longitude = float(form.get(key + '_lng') or 0)
            except ValueError:
                return {}
            if not (latitude or longitude):
                return {}
            return {'value_latitude': latitude, 'value_longitude': longitude}
        if kind in ('image', 'file'):
            upload = files.get(key)
            if not upload or not upload.filename:
                return {}
            content = upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                _logger.info('Questionnaire upload too large on checklist line %s', self.id)
                return {}
            if kind == 'image':
                return {'value_image': base64.b64encode(content)}
            return {'value_file': base64.b64encode(content), 'value_file_name': upload.filename}
        return {}

    def _talent_to_utc(self, local):
        """A datetime typed by the applicant (in the recruiter's time zone) as UTC."""
        return self.checklist_id._talent_tz().localize(local).astimezone(pytz.utc).replace(tzinfo=None)
