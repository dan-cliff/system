# -*- coding: utf-8 -*-
import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..lib import docx_html, docx_merge
from .signr_merge import (RELATIONAL, SIGNER_DETAILS, SPECIAL_ROOTS, X2MANY, MergeResolver,
                          describe_code, mergeable, special_model)

_logger = logging.getLogger(__name__)

# Where a template's signer comes from: code depends on these values.
SIGNER_SOURCES = [
    ('field', 'Field on the Record'),
    ('record', 'The Record Itself'),
    ('fixed', 'Fixed Contact'),
    ('sender', 'The Sender'),
    ('manual', 'Chosen When Sending'),
]
# Models whose records lead to a contact who can sign.
CONTACT_MODELS = ('res.partner', 'res.users', 'hr.employee', 'hr.applicant', 'hr.candidate')


def contact_of(record):
    """The contact (res.partner) who signs for a record of CONTACT_MODELS."""
    if not record:
        return record.env['res.partner']
    record = record[:1]
    if record._name == 'res.partner':
        return record
    if record._name == 'res.users':
        return record.partner_id
    if record._name == 'hr.employee':
        return (record.work_contact_id if 'work_contact_id' in record._fields else record.env['res.partner']) \
            or (record.user_id.partner_id if 'user_id' in record._fields else record.env['res.partner'])
    if 'partner_id' in record._fields:
        return record.partner_id
    return record.env['res.partner']


class SignrTemplate(models.Model):
    _name = 'signr.template'
    _description = "Sign'r Template"
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char('Template Name', required=True, tracking=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    document_type_id = fields.Many2one('signr.document.type', string='Document Type', tracking=True,
                                       ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company, tracking=True)
    description = fields.Text('Description')

    app_id = fields.Many2one(
        'ir.module.module', string='App', required=True, tracking=True, ondelete='cascade',
        domain="[('application', '=', True), ('state', '=', 'installed')]",
        help='The app whose records this document is made for (e.g. Employees for an employment contract).')
    available_model_ids = fields.Many2many('ir.model', compute='_compute_available_model_ids')
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, tracking=True, ondelete='cascade',
        domain="[('id', 'in', available_model_ids)]",
        help='The kind of record the merge codes read from (e.g. Employee). Sign requests are raised from '
             'records of this model.')
    model_name = fields.Char(related='model_id.model', string='Model Name', store=True, index=True)

    document = fields.Binary('Word Document', attachment=True, copy=True,
                             help='The Word (.docx) document, with a merge code wherever a value from the '
                                  'record goes. See the Merge Fields tab for the codes.')
    document_filename = fields.Char('File Name')
    field_ids = fields.One2many('signr.template.field', 'template_id', string='Codes in the Document',
                                copy=False)
    invalid_field_count = fields.Integer('Codes With Problems', compute='_compute_invalid_field_count')
    role_ids = fields.One2many('signr.template.role', 'template_id', string='Signers', copy=True)

    sign_in_order = fields.Boolean(
        'Sign in Order', default=True,
        help='Ask the signers one after the other, in the order of the list. When off, everyone is asked '
             'at once.')
    validity_days = fields.Integer(
        'Valid For (days)', default=30,
        help='Requests made from this template can be signed for this many days after they are sent. '
             '0 means they never expire.')
    email_subject = fields.Char('Email Subject', translate=True,
                                help='Leave empty to use "Please sign: <document>".')
    email_message = fields.Html('Email Message', translate=True,
                                help='Added to the email that asks each signer to sign.')
    request_ids = fields.One2many('signr.request', 'template_id', string='Sign Requests')
    request_count = fields.Integer('Sign Request Count', compute='_compute_request_count')

    # ------------------------------------------------------------------
    # App and model
    # ------------------------------------------------------------------
    @api.model
    def _signr_app_models(self, app):
        """The models an app works with: those its modules (and the add-ons that extend it)
        define, and those its menus open."""
        app = app.sudo()
        if not app:
            return self.env['ir.model']
        modules = app | app.downstream_dependencies().filtered(lambda m: not m.application)
        model_names = set(self.env['ir.model.data'].sudo().search([
            ('model', '=', 'ir.model'), ('module', 'in', modules.mapped('name')),
        ]).mapped(lambda data: self.env['ir.model'].sudo().browse(data.res_id).model))
        roots = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'ir.ui.menu'), ('module', 'in', modules.mapped('name')),
        ]).mapped('res_id')
        menus = self.env['ir.ui.menu'].sudo().with_context(active_test=False).search(
            [('id', 'child_of', self.env['ir.ui.menu'].sudo().browse(roots).filtered(
                lambda m: not m.parent_id).ids)])
        for menu in menus:
            action = menu.action
            if action and action._name == 'ir.actions.act_window' and action.res_model:
                model_names.add(action.res_model)
        models_ = self.env['ir.model'].sudo().search([
            ('model', 'in', list(model_names)), ('transient', '=', False)])
        return models_.filtered(lambda m: m.model in self.env and not self.env[m.model]._abstract
                                and not m.model.startswith(('ir.', 'mail.', 'bus.', 'signr.')))

    @api.depends('app_id')
    def _compute_available_model_ids(self):
        for template in self:
            template.available_model_ids = self._signr_app_models(template.app_id)

    @api.onchange('app_id')
    def _onchange_app_id(self):
        if self.model_id and self.model_id not in self.available_model_ids:
            self.model_id = False
        if not self.model_id and len(self.available_model_ids) == 1:
            self.model_id = self.available_model_ids

    def _compute_request_count(self):
        counts = dict(self.env['signr.request']._read_group(
            [('template_id', 'in', self.ids)], ['template_id'], ['__count']))
        for template in self:
            template.request_count = counts.get(template, 0)

    @api.depends('field_ids.valid')
    def _compute_invalid_field_count(self):
        for template in self:
            template.invalid_field_count = len(template.field_ids.filtered(lambda f: not f.valid))

    # ------------------------------------------------------------------
    # The Word document
    # ------------------------------------------------------------------
    def _document_bytes(self):
        self.ensure_one()
        data = self.with_context(bin_size=False).sudo().document
        return base64.b64decode(data) if data else b''

    @api.constrains('document')
    def _check_document(self):
        for template in self:
            data = template._document_bytes()
            if not data:
                continue
            try:
                docx_merge.find_codes(data)
            except docx_merge.DocxError as error:
                raise ValidationError(self.env._('%(template)s: %(error)s Save it from Word as a '
                                                 '"Word Document (.docx)".', template=template.name,
                                                 error=self.env._(str(error))))

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates.filtered('document')._signr_scan_document()
        return templates

    def write(self, vals):
        result = super().write(vals)
        if 'document' in vals or 'model_id' in vals:
            self._signr_scan_document()
        return result

    def _signr_scan_document(self):
        """List the codes the document uses, and check each one against the model."""
        for template in self:
            commands = [fields.Command.clear()]
            data = template._document_bytes()
            if data and template.model_name in self.env:
                try:
                    codes = docx_merge.find_codes(data)
                except docx_merge.DocxError:
                    codes = []
                for sequence, code in enumerate(codes):
                    label, error = describe_code(self.env, template.model_name, code)
                    commands.append(fields.Command.create({
                        'sequence': sequence, 'code': code, 'label': label,
                        'valid': not error, 'note': error or False,
                    }))
            template.sudo().field_ids = commands

    def action_rescan_document(self):
        self._signr_scan_document()
        return True

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------
    def _signr_check_ready(self):
        self.ensure_one()
        if not self.document:
            raise UserError(self.env._('Upload the Word document of template "%s" first.', self.name))
        if self.model_name not in self.env:
            raise UserError(self.env._('The model of template "%s" is not installed any more.', self.name))
        broken = self.field_ids.filtered(lambda f: not f.valid)
        if broken:
            raise UserError(self.env._(
                'Template "%(template)s" has merge codes that do not match a field:\n%(codes)s\n\n'
                'Fix them in the Word document and upload it again.', template=self.name,
                codes='\n'.join(f'- {{{{ {f.code} }}}}: {f.note}' for f in broken)))

    def _signr_merge(self, record, request=None, with_signatures=False):
        """The document with the record's values, as (docx bytes, pdf bytes).

        Templates are set up by Sign'r administrators: their codes are read
        with full access, once the caller has checked the sender can read the
        record."""
        self.ensure_one()
        resolver = MergeResolver(record.sudo().with_context(lang=self.env.lang),
                                 request=request.sudo() if request else None,
                                 with_signatures=with_signatures)
        docx = docx_merge.merge(self._document_bytes(), resolver)
        return docx, self._signr_docx_to_pdf(docx)

    @api.model
    def _signr_docx_to_pdf(self, docx):
        pdf = docx_html.libreoffice_to_pdf(docx)
        if pdf:
            return pdf
        html = docx_html.to_html(docx)
        return self.env['ir.actions.report'].sudo()._run_wkhtmltopdf(
            [html], specific_paperformat_args={
                'data-report-margin-top': 20, 'data-report-margin-bottom': 20,
                'data-report-header-spacing': 0,
            })

    def action_view_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('signr.action_signr_request')
        action['domain'] = [('template_id', '=', self.id)]
        action['context'] = {'default_template_id': self.id}
        return action

    def action_download_document(self):
        self.ensure_one()
        if not self.document:
            raise UserError(self.env._('This template has no Word document yet.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/signr.template/{self.id}/document/{self.document_filename or "template.docx"}'
                   '?download=true',
            'target': 'self',
        }

    # ------------------------------------------------------------------
    # Merge field browser (static/src/merge_fields)
    # ------------------------------------------------------------------
    @api.model
    def signr_merge_fields(self, model_name, path=None, signer_names=None):
        """The fields offered at one level of the merge field browser.

        ``path`` is the list of field names followed from the template's
        model (or a special root: company, user). Returns the level's model
        name and its fields, each with the code to copy into Word."""
        if model_name not in self.env:
            return {'model': '', 'fields': [], 'specials': []}
        path = [p for p in (path or []) if p]
        model = self.env[model_name]
        labels = []
        in_loop = False
        for index, name in enumerate(path):
            if index == 0 and name not in model._fields and special_model(self.env, name):
                model = self.env[special_model(self.env, name)]
                labels.append(self.env._(SPECIAL_ROOTS[name]))
                continue
            field = model._fields.get(name)
            if field is None or field.type not in RELATIONAL:
                return {'model': '', 'fields': [], 'specials': [], 'labels': labels}
            in_loop = in_loop or field.type in X2MANY
            labels.append(field._description_string(self.env))
            model = self.env[field.comodel_name]
        prefix = '.'.join(path)
        result = []
        try:
            descriptions = model.fields_get(attributes=['string', 'type', 'relation', 'help'])
        except Exception:  # noqa: BLE001 - a model the user can't read shows no fields
            descriptions = {}
        for name, description in descriptions.items():
            if not mergeable(name, description):
                continue
            result.append({
                'name': name,
                'label': description.get('string') or name,
                'type': description.get('type'),
                'relation': description.get('relation') or False,
                'help': description.get('help') or '',
                'code': f'{prefix}.{name}' if prefix else name,
                'expandable': description.get('type') in RELATIONAL and len(path) < 4,
                'repeats': description.get('type') in X2MANY,
            })
        result.sort(key=lambda f: (f['label'] or '').lower())
        specials = []
        if not path:
            specials.append({'title': self.env._('General'), 'items': [
                {'label': self.env._(SPECIAL_ROOTS['today']), 'code': 'today', 'type': 'date'},
                {'label': self.env._(SPECIAL_ROOTS['now']), 'code': 'now', 'type': 'datetime'},
                {'label': self.env._('Company (sending the request)'), 'code': 'company', 'type': 'many2one',
                 'expandable': True},
                {'label': self.env._('Sender (the person sending the request)'), 'code': 'user',
                 'type': 'many2one', 'expandable': True},
            ]})
            names = signer_names or []
            for number in range(1, max(len(names), 1) + 1):
                role = names[number - 1] if number <= len(names) else ''
                specials.append({
                    'title': self.env._('Signer %(number)s%(role)s', number=number,
                                        role=f' – {role}' if role else ''),
                    'items': [{'label': self.env._(label), 'code': f'signer_{number}.{detail}',
                               'type': 'signature' if detail == 'signature' else 'char'}
                              for detail, label in SIGNER_DETAILS.items()],
                })
        return {
            'model': model._name,
            'model_label': self.env['ir.model']._get(model._name).name,
            'labels': labels,
            'in_loop': in_loop,
            'fields': result,
            'specials': specials,
        }


class SignrTemplateRole(models.Model):
    _name = 'signr.template.role'
    _description = "Sign'r Template Signer"
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one('signr.template', string='Template', required=True, ondelete='cascade',
                                  index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True)
    model_id = fields.Many2one(related='template_id.model_id')
    sequence = fields.Integer('Order', default=10)
    name = fields.Char('Signs As', required=True, translate=True,
                       help='E.g. Employee, Manager, Customer. Shown to the signer and on the signed PDF.')
    signer_source = fields.Selection(SIGNER_SOURCES, string='Signer', required=True, default='field')
    partner_field_id = fields.Many2one(
        'ir.model.fields', string='Contact Field', ondelete='cascade',
        domain="[('model_id', '=', model_id), ('ttype', '=', 'many2one'), ('relation', 'in', "
               "('res.partner', 'res.users', 'hr.employee', 'hr.applicant', 'hr.candidate'))]",
        help='The field of the record that holds the person who signs (a contact, user or employee).')
    partner_id = fields.Many2one('res.partner', string='Contact',
                                 help='Always this contact, e.g. the director who countersigns.')

    @api.constrains('signer_source', 'partner_field_id', 'partner_id')
    def _check_source(self):
        for role in self:
            if role.signer_source == 'field' and not role.partner_field_id:
                raise ValidationError(self.env._('Pick the Contact Field for signer "%s".', role.name))
            if role.signer_source == 'fixed' and not role.partner_id:
                raise ValidationError(self.env._('Pick the Contact for signer "%s".', role.name))
            if role.signer_source == 'record' and role.template_id.model_name not in CONTACT_MODELS:
                raise ValidationError(self.env._(
                    'Signer "%s": the record itself can only sign when it is a contact, user, employee or '
                    'applicant.', role.name))

    def _signr_partner(self, record, sender):
        """Who signs as this role for a record, or an empty recordset."""
        self.ensure_one()
        partners = self.env['res.partner']
        if self.signer_source == 'fixed':
            return self.partner_id
        if self.signer_source == 'sender':
            return sender.partner_id
        if not record:
            return partners
        record = record.sudo()
        if self.signer_source == 'record':
            return contact_of(record)
        field_name = self.sudo().partner_field_id.name
        if self.signer_source == 'field' and field_name in record._fields:
            return contact_of(record[field_name])
        return partners


class SignrTemplateField(models.Model):
    _name = 'signr.template.field'
    _description = "Sign'r Template Merge Code"
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one('signr.template', string='Template', required=True, ondelete='cascade',
                                  index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    code = fields.Char('Merge Code', required=True)
    label = fields.Char('Field')
    valid = fields.Boolean('Valid')
    note = fields.Char('Problem')
