# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models


# ── Merge-field rendering helpers ───────────────────────────────────────────

def _traverse_path(record, path):
    """Walk a dot-notation field path and return a friendly string value."""
    obj = record
    parts = path.split('.')
    for i, part in enumerate(parts):
        if obj is None or obj is False:
            return ''
        # Special aliases
        if part == 'membership_type_label':
            return record.product_id.name or ''
        obj = getattr(obj, part, None)
    return _friendly(obj, record, path)


def _friendly(val, record, path=''):
    """Convert an ORM value to a human-readable string."""
    if val is None or val is False:
        return ''
    # Date / Datetime
    if hasattr(val, 'strftime'):
        if hasattr(val, 'hour') and hasattr(val, 'minute'):
            return val.strftime('%d/%m/%Y %H:%M')
        return val.strftime('%d/%m/%Y')
    # Many2one recordset
    if hasattr(val, '_name') and hasattr(val, 'id'):
        return getattr(val, 'name', '') or str(val.id)
    # One2many / Many2many recordsets
    if hasattr(val, '_ids'):
        return ', '.join(
            getattr(r, 'name', str(r.id)) for r in val
        )
    # Float / Monetary
    if isinstance(val, float):
        return f'{val:,.2f}'
    return str(val)


_MERGE_RE = re.compile(r'\[\[([^\]]+)\]\]')


class MembershipEmailTemplate(models.Model):
    _name = 'membership.email.template'
    _description = 'Membership Email Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    subject = fields.Char(
        string='Subject',
        help='Use [[field_name]] merge codes, e.g. [[name]] or [[partner_id.name]].',
    )
    body_html = fields.Html(
        string='Body',
        sanitize=False,
        help='Use [[field_name]] merge codes in the body text.',
    )

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'membership_email_tmpl_att_rel',
        'template_id', 'attachment_id',
        string='Default Attachments',
        help='Files uploaded here will be attached by default when this template is used.',
    )

    # ── Rendering ────────────────────────────────────────────────────────

    def _render_for_membership(self, membership):
        """Return (subject, body_html) with [[field]] codes replaced for a membership record."""
        self.ensure_one()

        def replace(match):
            path = match.group(1).strip()
            return _traverse_path(membership, path)

        rendered_subject = _MERGE_RE.sub(replace, self.subject or '')
        rendered_body = _MERGE_RE.sub(replace, self.body_html or '')
        return rendered_subject, rendered_body

    # ── Field browser action ─────────────────────────────────────────────

    def action_open_field_browser(self):
        """Open the merge-field browser dialog."""
        self.ensure_one()
        browser = self.env['membership.email.field.browser'].create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Available Merge Fields',
            'res_model': 'membership.email.field.browser',
            'res_id': browser.id,
            'view_mode': 'form',
            'target': 'new',
        }


# ── Merge field table ────────────────────────────────────────────────────────

_FIELDS = [
    ('Member Number',       'name',              'MBR-00001'),
    ('Member Name',         'partner_name',      'Jane Smith'),
    ('Contact Email',       'email',             'jane@example.com'),
    ('Contact Phone',       'phone',             '+61 400 000 000'),
    ('Membership Product',  'product_id.name',   'Annual Membership'),
    ('Status',              'status_id.name',    'Active'),
    ('Issued Date',         'date_issued',       '01/01/2026'),
    ('Expiry Date',         'date_expiry',       '31/12/2026'),
    ('Street',              'street',            '123 Main St'),
    ('City',                'city',              'Brisbane'),
    ('State',               'state_id.name',     'Queensland'),
    ('Country',             'country_id.name',   'Australia'),
]


class MembershipEmailFieldBrowser(models.TransientModel):
    _name = 'membership.email.field.browser'
    _description = 'Membership Email Field Browser'

    field_table = fields.Html(
        string='Available Merge Fields',
        compute='_compute_field_table',
        sanitize=False,
    )

    @api.depends()
    def _compute_field_table(self):
        rows = ''.join(
            f'<tr style="border-bottom: 1px solid #eee;">'
            f'<td style="padding: 5px 10px;">{label}</td>'
            f'<td style="padding: 5px 10px; font-family: monospace; '
            f'background: #f5f5f5; border-radius: 3px;">[[ {field} ]]</td>'
            f'<td style="padding: 5px 10px; color: #888; font-size: 0.85em;">{example}</td>'
            f'</tr>'
            for label, field, example in _FIELDS
        )
        table = (
            '<p style="margin-bottom: 10px;">'
            'Copy a <strong>Merge Code</strong> and paste it anywhere in your '
            'template Subject or Body. Values are substituted when the email is sent.'
            '</p>'
            '<table style="width:100%; border-collapse: collapse; font-size: 0.9em;">'
            '<thead><tr style="background:#f0f0f0; font-weight: bold;">'
            '<th style="padding:5px 10px; text-align:left;">Field</th>'
            '<th style="padding:5px 10px; text-align:left;">Merge Code</th>'
            '<th style="padding:5px 10px; text-align:left;">Example value</th>'
            '</tr></thead>'
            f'<tbody>{rows}</tbody>'
            '</table>'
        )
        for rec in self:
            rec.field_table = table
