# -*- coding: utf-8 -*-
"""What the merge codes of a template mean, and their values for a record.

A code is a path of field names from the template's model, joined by dots:
``job_id.name`` is the name of the record's Job Position. A path can go
through any Many2one, One2many or Many2many field. Besides the record's
fields, a code can start with:

- ``today`` / ``now``: the date (dd/mm/yyyy) or date and time it is merged;
- ``company.<field>``: the company sending the request;
- ``user.<field>``: the person sending it;
- ``signer_<n>.<detail>``: the n-th signer (1 = first): ``name``, ``email``,
  ``role``, ``signed_on`` or ``signature`` (their signature, as a picture,
  once they have signed).
"""
import base64
import re

from odoo import fields
from odoo.tools import html2plaintext
from odoo.tools.misc import formatLang

from ..lib.docx_merge import Image

SIGNER_RE = re.compile(r'^signer_(\d+)$')
SIGNER_DETAILS = {
    'name': 'Name',
    'email': 'Email',
    'role': 'Signs As',
    'signed_on': 'Signed On',
    'signature': 'Signature',
}
SPECIAL_ROOTS = {
    'today': "Today's Date",
    'now': 'Date and Time Now',
    'company': 'Company',
    'user': 'Sender',
}
RELATIONAL = ('many2one', 'one2many', 'many2many')
X2MANY = ('one2many', 'many2many')
# Never offered as merge fields: internals, chatter and passwords.
HIDDEN_FIELDS = {'id', '__last_update', 'display_name', 'password', 'new_password', 'access_token',
                 'access_url', 'access_warning', 'signup_token', 'totp_secret', 'api_key_ids'}
HIDDEN_PREFIXES = ('message_', 'activity_', 'website_message', 'org_show_', 'signr_', '_', 'avatar_')
# Smaller copies of a picture: the full-size one (image_1920) is offered instead.
HIDDEN_SUFFIXES = ('_128', '_256', '_512', '_1024')
HIDDEN_TYPES = {'json', 'properties', 'properties_definition', 'reference', 'many2one_reference'}


def mergeable(name, field):
    """Whether a field (a fields_get description) is offered as a merge field."""
    return not (name in HIDDEN_FIELDS or name.startswith(HIDDEN_PREFIXES)
                or field.get('type') in HIDDEN_TYPES
                or (field.get('type') in ('binary', 'image') and name.endswith(HIDDEN_SUFFIXES)))


def special_model(env, root):
    return {'company': 'res.company', 'user': 'res.users'}.get(root)


class MergeResolver:
    """Gives the values of a template's codes for one record (see lib/docx_merge.py)."""

    def __init__(self, record, request=None, with_signatures=False):
        self.record = record
        self.env = record.env
        self.request = request
        self.with_signatures = with_signatures
        self.company = (request.company_id if request else None) or self.env.company
        self.user = (request.user_id if request else None) or self.env.user
        self.tz = self.user.tz or self.company.partner_id.tz or 'UTC'

    # -- formatting -------------------------------------------------------
    def _format(self, records, field):
        if not records:
            return ''
        if len(records) > 1:
            values = []
            for record in records:
                value = self._format(record, field)
                if isinstance(value, str) and value and value not in values:
                    values.append(value)
            return ', '.join(values)
        value = records[field.name]
        kind = field.type
        if kind == 'boolean':
            return self.env._('Yes') if value else self.env._('No')
        if kind in ('binary', 'image'):
            if not value:
                return ''
            try:
                return Image(base64.b64decode(value))
            except (TypeError, ValueError):
                return ''
        if value in (False, None) and kind not in ('integer', 'float', 'monetary'):
            return ''
        if kind == 'many2one':
            return value.display_name or ''
        if kind in X2MANY:
            return ', '.join(name for name in value.mapped('display_name') if name)
        if kind == 'date':
            return value.strftime('%d/%m/%Y')
        if kind == 'datetime':
            local = fields.Datetime.context_timestamp(records.with_context(tz=self.tz), value)
            return local.strftime('%d/%m/%Y %H:%M')
        if kind == 'selection':
            labels = dict(field._description_selection(self.env))
            return str(labels.get(value, value or ''))
        if kind == 'monetary':
            currency_field = (field.get_currency_field(records) if hasattr(field, 'get_currency_field')
                              else field.currency_field)
            currency = records[currency_field] if currency_field in records._fields else None
            return formatLang(self.env, value or 0.0, currency_obj=currency or self.company.currency_id)
        if kind == 'float':
            digits = field.get_digits(self.env)
            return formatLang(self.env, value or 0.0, digits=digits[1] if digits else 2)
        if kind == 'integer':
            return str(value or 0)
        if kind == 'html':
            return html2plaintext(value or '').strip()
        return str(value)

    def _path(self, records, segments):
        """The value at the end of a path of field names, or None if the path is wrong."""
        if not segments:
            return ', '.join(records.mapped('display_name'))
        current = records
        for index, name in enumerate(segments):
            field = current._fields.get(name)
            if field is None:
                return None
            if index == len(segments) - 1:
                return self._format(current, field)
            if field.type not in RELATIONAL:
                return None
            current = current.mapped(name)
        return ''

    # -- signers ----------------------------------------------------------
    def _signer(self, number, detail):
        if detail not in SIGNER_DETAILS and detail is not None:
            return None
        signers = self.request.signer_ids.sorted(lambda s: (s.sequence, s.id)) if self.request else []
        signer = signers[number - 1] if 0 < number <= len(signers) else None
        if signer is None:
            return ''
        if detail in (None, 'name'):
            return signer.signed_by or signer.partner_id.name or ''
        if detail == 'email':
            return signer.partner_id.email or ''
        if detail == 'role':
            return signer.role or ''
        if detail == 'signed_on':
            return signer._format_signed_on() if signer.state == 'signed' else ''
        if detail == 'signature':
            if self.with_signatures and signer.state == 'signed' and signer.signature:
                return Image(base64.b64decode(signer.signature), max_width_cm=5.0, max_height_cm=2.5)
            return ''
        return ''

    # -- resolver API ------------------------------------------------------
    def value(self, code, prefix=None, scope=None):
        if prefix and scope is not None:
            if code == prefix:
                return scope.display_name or ''
            if code.startswith(prefix + '.'):
                return self._path(scope, code[len(prefix) + 1:].split('.'))
        segments = [segment for segment in code.split('.') if segment]
        if not segments:
            return None
        root = segments[0]
        if root in self.record._fields:
            return self._path(self.record, segments)
        if root == 'today' and len(segments) == 1:
            return fields.Date.context_today(self.record.with_context(tz=self.tz)).strftime('%d/%m/%Y')
        if root == 'now' and len(segments) == 1:
            now = fields.Datetime.context_timestamp(self.record.with_context(tz=self.tz), fields.Datetime.now())
            return now.strftime('%d/%m/%Y %H:%M')
        if root == 'company':
            return self._path(self.company, segments[1:]) if len(segments) > 1 else self.company.name
        if root == 'user':
            return self._path(self.user, segments[1:]) if len(segments) > 1 else self.user.name
        match = SIGNER_RE.match(root)
        if match and len(segments) <= 2:
            return self._signer(int(match.group(1)), segments[1] if len(segments) == 2 else None)
        return None

    def loop_prefix(self, code):
        model = self.record
        segments = code.split('.')
        for index, name in enumerate(segments):
            field = model._fields.get(name)
            if field is None:
                return None
            if field.type in X2MANY:
                return '.'.join(segments[:index + 1]) if index < len(segments) - 1 else None
            if field.type != 'many2one':
                return None
            model = self.env[field.comodel_name]
        return None

    def loop_scopes(self, prefix):
        return list(self.record.mapped(prefix))


def describe_code(env, model_name, code):
    """(label, error) for a code on a model: the labels of its path, or why it is wrong."""
    _ = env._
    segments = [segment for segment in (code or '').split('.')]
    if not code or not all(segments):
        return '', _('This code is empty or has an empty part.')
    model = env[model_name]
    root = segments[0]
    labels = []
    if root not in model._fields:
        if root in ('today', 'now'):
            if len(segments) > 1:
                return '', _('"%s" has no parts after it.', root)
            return _(SPECIAL_ROOTS[root]), ''
        if root in ('company', 'user'):
            labels.append(_(SPECIAL_ROOTS[root]))
            model = env[special_model(env, root)]
            segments = segments[1:]
            if not segments:
                return labels[0], ''
        else:
            match = SIGNER_RE.match(root)
            if match:
                if int(match.group(1)) < 1:
                    return '', _('Signers are numbered from 1.')
                if len(segments) > 2 or (len(segments) == 2 and segments[1] not in SIGNER_DETAILS):
                    return '', _('A signer code ends with one of: %s.', ', '.join(SIGNER_DETAILS))
                label = _('Signer %s', match.group(1))
                if len(segments) == 2:
                    label += ' › ' + _(SIGNER_DETAILS[segments[1]])
                return label, ''
            return '', _('"%(name)s" is not a field of %(model)s.', name=root,
                         model=env['ir.model']._get(model_name).name)
    for index, name in enumerate(segments):
        field = model._fields.get(name)
        if field is None:
            return ' › '.join(labels), _('"%(name)s" is not a field of %(model)s.', name=name,
                                        model=env['ir.model']._get(model._name).name)
        labels.append(field._description_string(env))
        if index < len(segments) - 1:
            if field.type not in RELATIONAL:
                return ' › '.join(labels), _('"%s" is not a link to other records, so nothing can follow it.', name)
            model = env[field.comodel_name]
    return ' › '.join(labels), ''
