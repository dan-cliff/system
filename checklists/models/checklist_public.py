# -*- coding: utf-8 -*-
"""Public submission: templates people outside Odoo can fill in.

A template with Public Submission turned on gets a secret link
(/checklists/public/<token>). Anyone with the link fills in its questions
plus their First Name, Last Name and Email or Phone Number; the checklist is
created completed, with the contact matched by email (or created) as its
Completed By.

Links can carry answers in their query string (built with the Public URL
Builder wizard): `first_name`, `last_name`, `email`, `phone` and
`q<question id>` for each question. The builder signs its links (`sig`, an
HMAC over the token and every other parameter), and only a signed link may
lock fields (`lock`, a comma-separated list of keys, shown read-only and
enforced on submit), answer Many2one / Many2Many questions (so a visitor
can't look up records by editing the link) or set the checklist fields the
public form leaves out: `user` (Completed By), `company`, and with the
add-ons `asset` and the Organisation levels (see _public_link_record_fields).
Those are never shown on the form; they are saved on the checklist.
"""
import base64
import re
import secrets
from datetime import datetime
from urllib.parse import urlencode

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import consteq
from odoo.tools.mail import email_normalize
from odoo.tools.misc import hmac as odoo_hmac
from odoo.tools.safe_eval import safe_eval

from .checklist_question_condition import MULTI_OPTION_TYPES, SINGLE_OPTION_TYPES
from .checklist_template import LAYOUT_TYPES, RELATION_TYPES

PUBLIC_ROUTE = '/checklists/public/'
# Query string keys for the contact details, in the order the form shows them.
CONTACT_KEYS = ('first_name', 'last_name', 'email', 'phone')
# Query string keys that aren't answers.
LOCK_KEY = 'lock'
SIGNATURE_KEY = 'sig'
TZ_KEY = 'tz'
SIGNATURE_SCOPE = 'checklists.public_url'
# Answers a link can't carry (uploads) or that aren't answers (layout).
NOT_PREFILLABLE_TYPES = LAYOUT_TYPES + ('image', 'file')
DATE_FORMATS = ('%d/%m/%Y', '%Y-%m-%d')
DATETIME_FORMATS = ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S')
TRUE_VALUES = ('1', 'true', 'yes', 'y', 'on')
# Largest upload accepted per Image / File question.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def question_key(question_id):
    """The query string / form key of a question's answer."""
    return f'q{question_id}'


def _parse_with(value, formats):
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _tz(name):
    try:
        return pytz.timezone(name) if name else pytz.utc
    except pytz.UnknownTimeZoneError:
        return pytz.utc


class ChecklistTemplate(models.Model):
    _inherit = 'checklist.template'

    public_enabled = fields.Boolean(
        string='Public Submission',
        help='Anyone with the public link can fill in this checklist, without logging in. '
             'They give their name and email or phone number instead of the Completed By, '
             'Asset, Company and Organisation fields.',
    )
    public_token = fields.Char(string='Public Access Token', copy=False, readonly=True)
    public_url = fields.Char(string='Public Access URL', compute='_compute_public_url')
    public_company_id = fields.Many2one(
        'res.company', string='Submissions Company', default=lambda self: self.env.company,
        help='The company of checklists submitted through the public link.',
    )
    public_thank_you = fields.Text(
        string='Thank You Message', translate=True,
        help='Shown once a public checklist has been submitted.',
    )

    _public_token_uniq = models.Constraint('UNIQUE (public_token)', 'Another template already has this public token.')

    @api.depends('public_enabled', 'public_token')
    def _compute_public_url(self):
        for template in self:
            template.public_url = (
                template.get_base_url() + PUBLIC_ROUTE + template.public_token
                if template.public_enabled and template.public_token else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('public_enabled') and not vals.get('public_token'):
                vals['public_token'] = self._new_public_token()
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if vals.get('public_enabled'):
            for template in self.filtered(lambda t: not t.public_token):
                template.public_token = self._new_public_token()
        return result

    @api.model
    def _new_public_token(self):
        return secrets.token_urlsafe(24)

    def action_regenerate_public_token(self):
        """A new link: the old one, and every link built from it, stop working."""
        for template in self:
            template.public_token = self._new_public_token()

    def action_open_public_url_wizard(self):
        self.ensure_one()
        if not (self.public_enabled and self.public_token):
            raise UserError(self.env._('Turn on Public Submission for this template first.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Public URL Builder'),
            'res_model': 'checklist.public.url.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_id': self.id},
        }

    # ── Signed links ─────────────────────────────────────────────────────

    def _public_signature(self, params):
        """HMAC over the token and the (key, value) parameters, in any order."""
        self.ensure_one()
        message = self.public_token + '?' + urlencode(sorted(
            (key, value) for key, value in params if key != SIGNATURE_KEY))
        return odoo_hmac(self.env(su=True), SIGNATURE_SCOPE, message)

    def _public_url_for(self, params):
        """The public link carrying `params` [(key, value)], signed."""
        self.ensure_one()
        if not self.public_url:
            return False
        if not params:
            return self.public_url
        params = list(params) + [(SIGNATURE_KEY, self._public_signature(params))]
        return self.public_url + '?' + urlencode(params)

    def _public_read_link(self, args):
        """What a link's query string asks for.

        Returns (values, locked, trusted): values {key: str} for the contact
        keys and the template's questions; locked, the keys a signed link
        locks; trusted, whether the link carries a valid signature. Unsigned
        links can't lock fields or answer Many2one / Many2Many questions.
        """
        self.ensure_one()
        params = [(key, value) for key, value in args.items(multi=True) if key != SIGNATURE_KEY]
        signature = args.get(SIGNATURE_KEY) or ''
        trusted = bool(signature) and consteq(signature, self._public_signature(params))
        questions = {question_key(q.id): q for q in self._public_questions()}
        record_keys = self._public_link_record_fields()
        values = {}
        for key, value in params:
            if key in CONTACT_KEYS or key == TZ_KEY:
                values[key] = value
            elif key in record_keys:
                if trusted:
                    values[key] = value
            elif key in questions and questions[key].question_type not in NOT_PREFILLABLE_TYPES:
                if questions[key].question_type in RELATION_TYPES and not trusted:
                    continue
                values[key] = value
        locked = set()
        if trusted:
            locked = {key.strip() for key in (args.get(LOCK_KEY) or '').split(',')} & set(values)
        return values, locked, trusted

    # ── Checklist fields set by the link ─────────────────────────────────

    @api.model
    def _public_link_record_fields(self):
        """{query key: checklist field} a signed link can set: fields the
        public form leaves out (add-ons add the asset and Organisation)."""
        return {'user': 'user_id', 'company': 'company_id'}

    def _public_link_record(self, field_name, record):
        """Whether a link may set the checklist's `field_name` to `record`
        (an existing record of its model). Extended by add-ons."""
        self.ensure_one()
        if field_name == 'user_id':
            return record.active and not record.share
        return True

    def _public_link_vals(self, values):
        """Checklist values for the fields a signed link sets (values from
        _public_read_link); ids that are gone or not allowed are ignored."""
        self.ensure_one()
        Checklist = self.env['checklist.checklist'].sudo()
        vals = {}
        for key, field_name in self._public_link_record_fields().items():
            raw = (values.get(key) or '').strip()
            if not raw.isdigit() or field_name not in Checklist._fields:
                continue
            record = self.env[Checklist._fields[field_name].comodel_name].sudo().browse(int(raw)).exists()
            if record and self.sudo()._public_link_record(field_name, record):
                vals[field_name] = record.id
        return vals

    # ── Form ─────────────────────────────────────────────────────────────

    def _public_questions(self):
        self.ensure_one()
        return self.sudo().question_ids.sorted(lambda q: (q.sequence, q.id))

    def _public_condition_context(self):
        """{question id: {'user': bool, 'record': bool}} for the Current User
        and Checklist filters of conditional questions, evaluated for the
        visitor (the public user) and a checklist from this template."""
        self.ensure_one()
        Checklist = self.env['checklist.checklist'].sudo()
        checklist = None
        result = {}
        for question in self._public_questions().filtered('conditional'):
            context = {}
            user_domain = question._public_eval_domain(question.condition_user_domain)
            if user_domain:
                context['user'] = bool(self.env.user.sudo().filtered_domain(user_domain))
            record_domain = question._public_eval_domain(question.condition_record_domain)
            if record_domain:
                if checklist is None:
                    checklist = Checklist.new({
                        'template_id': self.id, 'company_id': self._public_company().id,
                        'is_public': True,
                    })
                context['record'] = bool(checklist.filtered_domain(record_domain))
            result[question.id] = context
        return result

    def _public_company(self):
        self.ensure_one()
        return self.sudo().public_company_id or self.env.company

    def _public_format_phone(self, number):
        """Odoo's phone formatting, for the submissions company's country."""
        self.ensure_one()
        country = self._public_company().country_id or self.env.company.country_id
        return self._phone_format_number(number, country, force_format='INTERNATIONAL') or number

    # ── Submission ───────────────────────────────────────────────────────

    def _public_submit(self, contact, answers, link_vals=None):
        """Create the completed checklist of a public submission.

        contact: {first_name, last_name, email, phone} (already checked);
        answers: {question id: line values}; link_vals: checklist values a
        signed link sets (_public_link_vals). Runs as superuser.
        """
        self.ensure_one()
        template = self.sudo()
        partner = template.env['res.partner']._checklist_public_partner(contact)
        checklist = template.env['checklist.checklist'].with_context(
            mail_create_nolog=True, tracking_disable=True,
        ).create({
            'template_id': template.id,
            'company_id': template._public_company().id,
            'user_id': False,
            'is_public': True,
            'partner_id': partner.id,
            'public_first_name': contact['first_name'],
            'public_last_name': contact['last_name'],
            'public_email': contact['email'] or False,
            'public_phone': contact['phone'] or False,
            **(link_vals or {}),
        })
        for line in checklist.line_ids:
            vals = answers.get(line.question_id.id)
            if vals:
                line.write(vals)
        checklist.state = 'done'
        checklist.message_post(
            body=self.env._('Submitted through the public link by %s.', partner.display_name),
            author_id=partner.id, message_type='comment', subtype_xmlid='mail.mt_note',
        )
        return checklist


class ChecklistQuestion(models.Model):
    _inherit = 'checklist.question'

    def _public_eval_domain(self, domain):
        try:
            value = safe_eval(domain or '[]', {'uid': self.env.uid, 'user': self.env.user})
        except Exception:  # noqa: BLE001 - a broken filter shows nothing rather than crashing the page
            return [(0, '=', 1)]
        return value if isinstance(value, list) else []

    def _public_relation_records(self, ids):
        """The records with these ids a Many2one / Many2Many answer may pick."""
        self.ensure_one()
        model = self.relation_model_id.model
        if not model or model not in self.env or not ids:
            return None
        domain = self._public_eval_domain(self.relation_domain)
        return self.env[model].sudo().search(domain + [('id', 'in', ids)])

    def _public_option_ids(self, raw):
        values = raw if isinstance(raw, (list, tuple)) else (raw or '').split(',')
        ids = []
        for value in values:
            value = str(value).strip()
            if value.isdigit():
                ids.append(int(value))
        valid = set(self.sudo().option_ids.ids)
        if any(i not in valid for i in ids):
            raise ValidationError(self.env._('"%s" has an answer that is not one of its options.', self.name))
        return ids

    def _public_line_vals(self, raw, tz_name=None):
        """Checklist line values for the answer `raw` (text from the form or
        a link; a list for multi-option questions; an uploaded file for
        Image / File). {} when unanswered. Raises ValidationError when the
        answer isn't valid for the question."""
        self.ensure_one()
        kind = self.question_type
        if kind in LAYOUT_TYPES or raw is None:
            return {}
        if kind in ('image', 'file'):
            return self._public_upload_vals(raw)
        if kind in MULTI_OPTION_TYPES:
            return {'value_option_ids': [fields.Command.set(self._public_option_ids(raw))]} if raw else {}
        text = raw.strip() if isinstance(raw, str) else ','.join(map(str, raw)).strip()
        if kind == 'boolean':
            return {'value_boolean': text.lower() in TRUE_VALUES}
        if not text:
            return {}
        if kind == 'text':
            return {'value_text': text}
        if kind == 'text_area':
            return {'value_text_area': raw.strip()}
        if kind in ('number', 'integer'):
            try:
                number = float(text.replace(',', ''))
            except ValueError:
                raise ValidationError(self.env._('"%s" needs a number.', self.name)) from None
            if kind == 'integer':
                if number != int(number):
                    raise ValidationError(self.env._('"%s" needs a whole number.', self.name))
                return {'value_integer': int(number)}
            return {'value_number': number}
        if kind == 'date':
            parsed = _parse_with(text, DATE_FORMATS)
            if not parsed:
                raise ValidationError(self.env._('"%s" needs a date as dd/mm/yyyy.', self.name))
            return {'value_date': parsed.date()}
        if kind == 'datetime':
            parsed = _parse_with(text, DATETIME_FORMATS)
            if not parsed:
                raise ValidationError(self.env._('"%s" needs a date and time as dd/mm/yyyy HH:MM.', self.name))
            utc = _tz(tz_name).localize(parsed).astimezone(pytz.utc).replace(tzinfo=None)
            return {'value_datetime': utc}
        if kind in SINGLE_OPTION_TYPES:
            ids = self._public_option_ids(text)
            return {'value_option_id': ids[0]} if ids else {}
        if kind == 'geolocation':
            try:
                latitude, longitude = (float(part) for part in text.split(','))
            except ValueError:
                raise ValidationError(self.env._('"%s" has a location that could not be read.', self.name)) from None
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValidationError(self.env._('"%s" has a location that could not be read.', self.name))
            vals = {'value_latitude': latitude, 'value_longitude': longitude}
            if self.geo_show_address:
                vals['value_address'] = self.env['checklist.line'].checklist_reverse_geocode(latitude, longitude)
            return vals
        if kind == 'phone':
            return {'value_phone': self.template_id._public_format_phone(text)}
        if kind == 'email':
            if not email_normalize(text):
                raise ValidationError(self.env._('"%s" needs a valid email address.', self.name))
            return {'value_email': text}
        if kind == 'website':
            return {'value_url': text if re.match(r'^[a-z][a-z0-9+.-]*://', text, re.I) else 'https://' + text}
        if kind in RELATION_TYPES:
            ids = [int(part) for part in text.split(',') if part.strip().isdigit()]
            records = self._public_relation_records(ids)
            if not records:
                return {}
            if kind == 'many2one':
                return {'value_reference': f'{records._name},{records[0].id}'}
            # Keep the link's order.
            return {'value_reference_ids': [i for i in ids if i in records.ids]}
        return {}

    def _public_upload_vals(self, upload):
        if not upload or not getattr(upload, 'filename', None):
            return {}
        content = upload.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            return {}
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationError(self.env._('The file for "%s" is larger than 20 MB.', self.name))
        data = base64.b64encode(content)
        if self.question_type == 'image':
            if not (upload.mimetype or '').startswith('image/'):
                raise ValidationError(self.env._('"%s" needs an image.', self.name))
            return {'value_image': data}
        return {'value_file': data, 'value_file_name': upload.filename}

    def _public_display(self, raw):
        """Display names of the records a link answers a Many2one / Many2Many with."""
        self.ensure_one()
        ids = [int(part) for part in (raw or '').split(',') if part.strip().isdigit()]
        records = self._public_relation_records(ids)
        if not records:
            return []
        by_id = {record.id: record.display_name for record in records}
        return [by_id[i] for i in ids if i in by_id]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _checklist_public_partner(self, contact):
        """The contact with the submission's email, or a new one from its
        details. An existing contact is never changed by a submission."""
        Partner = self.sudo()
        normalized = email_normalize(contact.get('email') or '')
        if normalized:
            partner = Partner.search([('email_normalized', '=', normalized)], order='is_company, id', limit=1)
            if partner:
                return partner
        return Partner.create({
            'name': ' '.join(filter(None, (contact['first_name'], contact['last_name']))),
            'email': contact.get('email') or False,
            'phone': contact.get('phone') or False,
        })
