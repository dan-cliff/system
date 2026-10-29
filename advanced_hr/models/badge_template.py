# -*- coding: utf-8 -*-
import base64
import re
import uuid

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import formatLang, html2plaintext
from odoo.tools.image import image_data_uri

PLACEHOLDER_RE = re.compile(r'\{\{\s*([A-Za-z_][\w.]*)\s*\}\}')
COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')
FONTS = {
    'Lato': "'Lato', 'Helvetica Neue', Arial, sans-serif",
    'Arial': 'Arial, Helvetica, sans-serif',
    'Helvetica': "'Helvetica Neue', Helvetica, Arial, sans-serif",
    'Verdana': 'Verdana, Geneva, sans-serif',
    'Georgia': 'Georgia, serif',
    'Times New Roman': "'Times New Roman', Times, serif",
    'Courier New': "'Courier New', Courier, monospace",
}
ELEMENT_TYPES = ('text', 'image', 'qr', 'barcode', 'shape')
# Colours used when the company has none set (house palette).
DEFAULT_PRIMARY = '#5B3DB8'
DEFAULT_SECONDARY = '#14A3A3'
# Codes are drawn at print resolution.
CODE_DPI = 300


def _default_layout():
    """A simple portrait card: company band, photo, name, job and a QR code."""
    return [
        {'id': 'band', 'type': 'shape', 'x': 0, 'y': 0, 'w': 54, 'h': 18, 'fill': 'company_primary'},
        {'id': 'logo', 'type': 'image', 'source': 'company_logo', 'x': 12, 'y': 3, 'w': 30, 'h': 12, 'fit': 'contain'},
        {'id': 'photo', 'type': 'image', 'source': 'employee_photo', 'x': 14, 'y': 22, 'w': 26, 'h': 30,
         'fit': 'cover', 'radius': 2},
        {'id': 'name', 'type': 'text', 'text': '{{ name }}', 'x': 3, 'y': 54, 'w': 48, 'h': 8,
         'size': 13, 'bold': True, 'align': 'center', 'valign': 'middle', 'color': '#2A3F8F'},
        {'id': 'job', 'type': 'text', 'text': '{{ job_title }}', 'x': 3, 'y': 62, 'w': 48, 'h': 5,
         'size': 8, 'align': 'center', 'valign': 'middle', 'color': 'company_secondary'},
        {'id': 'qr', 'type': 'qr', 'value': '{{ barcode }}', 'x': 20, 'y': 69, 'w': 14, 'h': 14},
    ]


class AdvancedHrBadgeTemplate(models.Model):
    _name = 'advanced.hr.badge.template'
    _description = 'ID Badge'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        help='Only offered to the employees of this company. Leave empty to offer it to every employee.')
    page_width = fields.Float(string='Width (mm)', required=True, default=54.0)
    page_height = fields.Float(string='Height (mm)', required=True, default=85.6)
    background_color = fields.Char(string='Background', default='#FFFFFF')
    background_image = fields.Image(string='Background Image', max_width=2048, max_height=2048)
    layout = fields.Json(string='Layout', default=lambda self: _default_layout())
    preview_employee_id = fields.Many2one(
        'hr.employee', string='Preview Employee',
        help='The employee whose details fill the badge in the designer.')
    report_action_id = fields.Many2one('ir.actions.report', string='Print Action', readonly=True, copy=False)
    paperformat_id = fields.Many2one('report.paperformat', string='Paper Format', readonly=True, copy=False)
    element_count = fields.Integer(compute='_compute_element_count')

    @api.depends('layout')
    def _compute_element_count(self):
        for template in self:
            template.element_count = len(template.layout or [])

    @api.constrains('page_width', 'page_height')
    def _check_page_size(self):
        for template in self:
            if not (10 <= template.page_width <= 450 and 10 <= template.page_height <= 450):
                raise ValidationError(self.env._('The badge page must be between 10 and 450 mm on each side.'))

    @api.constrains('background_color')
    def _check_background_color(self):
        for template in self:
            if template.background_color and not COLOR_RE.match(template.background_color):
                raise ValidationError(self.env._('The background colour must be a hex colour such as #FFFFFF.'))

    @api.constrains('layout')
    def _check_layout(self):
        for template in self:
            layout = template.layout or []
            if not isinstance(layout, list) or any(
                    not isinstance(el, dict) or el.get('type') not in ELEMENT_TYPES for el in layout):
                raise ValidationError(self.env._('The badge layout is not valid.'))

    # ── Print action (one per badge, listed on the employee's Print menu) ──

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._sync_report_action()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'active', 'company_id', 'page_width', 'page_height', 'sequence'} & set(vals):
            self._sync_report_action()
        return res

    def unlink(self):
        actions = self.sudo().report_action_id
        paperformats = self.sudo().paperformat_id
        res = super().unlink()
        actions.unlink()
        paperformats.unlink()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for template, vals in zip(self, vals_list):
            vals.setdefault('name', self.env._('%s (copy)', template.name))
        return vals_list

    def _sync_report_action(self):
        employee_model = self.env['ir.model']._get('hr.employee')
        for template in self.sudo():
            paperformat_vals = {
                'name': 'ID Badge: %s' % template.name,
                'format': 'custom',
                'page_width': max(1, round(template.page_width)),
                'page_height': max(1, round(template.page_height)),
                'orientation': 'Portrait',
                'margin_top': 0, 'margin_bottom': 0, 'margin_left': 0, 'margin_right': 0,
                'header_line': False, 'header_spacing': 0,
                'disable_shrinking': True, 'dpi': 96,
            }
            if template.paperformat_id:
                template.paperformat_id.write(paperformat_vals)
            else:
                template.paperformat_id = self.env['report.paperformat'].sudo().create(paperformat_vals)
            action_vals = {
                'name': template.name,
                'model': 'hr.employee',
                'report_type': 'qweb-pdf',
                'report_name': 'advanced_hr.report_badge',
                'report_file': 'advanced_hr.report_badge',
                'paperformat_id': template.paperformat_id.id,
                'print_report_name': "'%s - %%s' %% (object.name or '')" % template.name.replace("'", ''),
                'binding_model_id': employee_model.id if template.active else False,
                'binding_type': 'report',
                'domain': "[('company_id', '=', %d)]" % template.company_id.id if template.company_id else False,
                'badge_template_id': template.id,
            }
            if template.report_action_id:
                template.report_action_id.write(action_vals)
            else:
                template.report_action_id = self.env['ir.actions.report'].sudo().create(action_vals)

    def action_print_preview(self):
        self.ensure_one()
        employee = self.preview_employee_id or self.env['hr.employee'].search(
            ['|', ('company_id', '=', self.company_id.id), ('company_id', '=', False)] if self.company_id else [],
            limit=1)
        if not employee:
            raise UserError(self.env._('Add an employee first, or pick a Preview Employee.'))
        return self.report_action_id.report_action(employee, config=False)

    # ── Rendering ─────────────────────────────────────────────────────────

    @api.model
    def _badge_company(self, employee, company=None):
        return (employee and employee.company_id) or company or self.env.company

    @api.model
    def _badge_color(self, value, company, default=False):
        if value == 'company_primary':
            return company.primary_color if company.primary_color and COLOR_RE.match(company.primary_color) else DEFAULT_PRIMARY
        if value == 'company_secondary':
            return company.secondary_color if company.secondary_color and COLOR_RE.match(company.secondary_color) else DEFAULT_SECONDARY
        if value == 'transparent':
            return 'transparent'
        if isinstance(value, str) and COLOR_RE.match(value):
            return value
        return default

    @api.model
    def _badge_number(self, value, default=0.0, low=-1000.0, high=1000.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(number, low), high)

    @api.model
    def _badge_field_value(self, employee, path):
        """The value of a dotted field path on the employee, as text."""
        if not employee:
            return False
        record = employee
        names = path.split('.')
        try:
            for index, name in enumerate(names):
                field = record._fields.get(name)
                if not field:
                    return ''
                record._check_field_access(field, 'read')
                value = record[name] if len(record) <= 1 else record.mapped(name)
                last = index == len(names) - 1
                if field.type in ('many2one', 'one2many', 'many2many'):
                    if last:
                        return ', '.join(n for n in value.mapped('display_name') if n)
                    record = value[:1]
                    if not record:
                        return ''
                    continue
                if not last:
                    return ''
                return self._badge_format(record, field, value)
        except AccessError:
            return ''
        return ''

    @api.model
    def _badge_format(self, record, field, value):
        if field.type == 'boolean':
            return self.env._('Yes') if value else self.env._('No')
        if value is False or value is None:
            return ''
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        if field.type == 'date':
            return value.strftime('%d/%m/%Y')
        if field.type == 'datetime':
            return fields.Datetime.context_timestamp(record, value).strftime('%d/%m/%Y %H:%M')
        if field.type in ('float', 'monetary'):
            return formatLang(self.env, value)
        if field.type == 'binary':
            return ''
        if field.type == 'html':
            return html2plaintext(value).strip()
        return str(value)

    @api.model
    def _badge_fill(self, text, employee, labels=False):
        """Replace {{ field.path }} placeholders. Without an employee (designer
        preview) the field's label stands in, in square brackets."""
        if not text:
            return ''

        def replace(match):
            path = match.group(1)
            if labels or not employee:
                return '[%s]' % self._badge_path_label(path)
            return self._badge_field_value(employee, path) or ''
        return PLACEHOLDER_RE.sub(replace, str(text))

    @api.model
    def _badge_path_label(self, path):
        model = self.env['hr.employee']
        labels = []
        for name in path.split('.'):
            field = model._fields.get(name)
            if not field:
                labels.append(name)
                break
            labels.append(field._description_string(self.env))
            if field.relational:
                model = self.env[field.comodel_name]
            else:
                break
        return ' › '.join(labels)

    @api.model
    def _badge_code_image(self, kind, value, width_mm, height_mm, color=False, background=False):
        if not value:
            return False
        width = max(40, int(width_mm / 25.4 * CODE_DPI))
        height = max(40, int(height_mm / 25.4 * CODE_DPI))
        kwargs = {'width': width, 'height': height, 'humanreadable': 0, 'quiet': 1}
        if kind == 'qr':
            side = min(width, height)
            kwargs.update(width=side, height=side, barLevel='M')
            barcode_type = 'QR'
        else:
            barcode_type = 'Code128'
        try:
            png = self.env['ir.actions.report'].barcode(barcode_type, value, **kwargs)
        except (ValueError, AttributeError):
            return False
        return 'data:image/png;base64,%s' % base64.b64encode(png).decode()

    @api.model
    def _badge_image_src(self, element, employee, company):
        source = element.get('source')
        data = False
        if source == 'employee_photo':
            if employee:
                try:
                    data = employee.image_1920
                except AccessError:
                    data = False
            else:
                return '/advanced_hr/static/src/img/photo_placeholder.svg'
        elif source == 'company_logo':
            data = company.logo
        elif source == 'custom':
            src = element.get('src') or ''
            return src if src.startswith('data:image/') else False
        if not data:
            return False
        return image_data_uri(data if isinstance(data, bytes) else data.encode())

    @api.model
    def _badge_render_element(self, element, employee, company, labels=False):
        """Everything needed to draw one element (same in the designer and the PDF)."""
        kind = element.get('type')
        num = self._badge_number
        x, y = num(element.get('x')), num(element.get('y'))
        w, h = max(num(element.get('w'), 10), 0.5), max(num(element.get('h'), 5), 0.5)
        style = [
            'position:absolute', 'left:%.2fmm' % x, 'top:%.2fmm' % y,
            'width:%.2fmm' % w, 'height:%.2fmm' % h, 'overflow:hidden',
        ]
        rotate = num(element.get('rotate'), 0, -360, 360)
        if rotate:
            style += ['-webkit-transform:rotate(%.1fdeg)' % rotate, 'transform:rotate(%.1fdeg)' % rotate]
        opacity = num(element.get('opacity'), 1, 0, 1)
        if opacity < 1:
            style.append('opacity:%.2f' % opacity)
        radius = num(element.get('radius'), 0, 0, 500)
        if radius:
            style.append('border-radius:%.2fmm' % radius)
        border_width = num(element.get('border_width'), 0, 0, 20)
        if border_width:
            style.append('border:%.2fmm solid %s' % (
                border_width, self._badge_color(element.get('border_color'), company, '#2A3F8F')))
            style.append('box-sizing:border-box')
        result = {'id': element.get('id') or uuid.uuid4().hex[:8], 'type': kind}

        if kind == 'shape':
            fill = self._badge_color(element.get('fill'), company, 'transparent')
            style.append('background-color:%s' % fill)
        elif kind == 'text':
            background = self._badge_color(element.get('background'), company, False)
            if background:
                style.append('background-color:%s' % background)
            text = self._badge_fill(element.get('text'), employee, labels=labels)
            cell = [
                'display:table-cell', 'width:%.2fmm' % w, 'height:%.2fmm' % h,
                'vertical-align:%s' % {'top': 'top', 'bottom': 'bottom'}.get(element.get('valign'), 'middle'),
                'text-align:%s' % {'center': 'center', 'right': 'right'}.get(element.get('align'), 'left'),
                'font-family:%s' % FONTS.get(element.get('font'), FONTS['Lato']),
                'font-size:%.2fpt' % num(element.get('size'), 10, 2, 200),
                'line-height:%.2f' % num(element.get('line_height'), 1.15, 0.5, 4),
                'color:%s' % self._badge_color(element.get('color'), company, '#2A3F8F'),
                'font-weight:%s' % ('bold' if element.get('bold') else 'normal'),
                'font-style:%s' % ('italic' if element.get('italic') else 'normal'),
                'text-decoration:%s' % ('underline' if element.get('underline') else 'none'),
                'word-wrap:break-word',
            ]
            if element.get('uppercase'):
                cell.append('text-transform:uppercase')
            result.update({
                'text': text,
                'lines': text.split('\n'),
                'cell_style': ';'.join(cell),
            })
        elif kind == 'image':
            src = self._badge_image_src(element, employee, company)
            fit = 'cover' if element.get('fit') == 'cover' else 'contain'
            if src:
                style += [
                    "background-image:url('%s')" % src,
                    'background-repeat:no-repeat', 'background-position:center center',
                    '-webkit-background-size:%s' % fit, 'background-size:%s' % fit,
                ]
            result['src'] = src
        elif kind in ('qr', 'barcode'):
            value = self._badge_fill(element.get('value'), employee, labels=False) if employee else (
                self._badge_fill(element.get('value'), False) or 'ID')
            background = self._badge_color(element.get('background'), company, False)
            if background:
                style.append('background-color:%s' % background)
            src = self._badge_code_image(kind, value, w, h)
            if src:
                style += [
                    "background-image:url('%s')" % src,
                    'background-repeat:no-repeat', 'background-position:center center',
                    '-webkit-background-size:contain', 'background-size:contain',
                ]
            result.update({'src': src, 'value': value})
        result['style'] = ';'.join(style)
        return result

    def _badge_page_style(self, company):
        self.ensure_one()
        style = [
            'position:relative', 'overflow:hidden',
            'width:%.2fmm' % self.page_width, 'height:%.2fmm' % self.page_height,
            'background-color:%s' % (self._badge_color(self.background_color, company, '#FFFFFF')),
        ]
        if self.background_image:
            style += [
                "background-image:url('data:image/png;base64,%s')" % self.background_image.decode(),
                '-webkit-background-size:100%% 100%%', 'background-size:100% 100%',
            ]
        return ';'.join(style)

    def _badge_render(self, employee):
        """The badge of one employee, for the PDF."""
        self.ensure_one()
        company = self._badge_company(employee, self.company_id)
        return {
            'page_style': Markup(self._badge_page_style(company)),
            'elements': [
                self._badge_render_element(element, employee, company)
                for element in (self.layout or []) if isinstance(element, dict)
            ],
        }

    # ── Designer ──────────────────────────────────────────────────────────

    @api.model
    def badge_designer_preview(self, layout, employee_id=False, company_id=False):
        """Resolved text and images for the designer's canvas."""
        employee = self.env['hr.employee'].browse(employee_id).exists() if employee_id else False
        company = self._badge_company(
            employee, self.env['res.company'].browse(company_id).exists() if company_id else None)
        elements = {}
        for element in layout or []:
            if not isinstance(element, dict) or element.get('type') not in ELEMENT_TYPES:
                continue
            rendered = self._badge_render_element(element, employee, company, labels=not employee)
            elements[rendered['id']] = {
                'text': rendered.get('text'),
                'src': rendered.get('src'),
                'cell_style': rendered.get('cell_style'),
                'style': rendered['style'],
            }
        return {
            'elements': elements,
            'colors': {
                'company_primary': self._badge_color('company_primary', company),
                'company_secondary': self._badge_color('company_secondary', company),
            },
            'company_name': company.name,
        }

    @api.model
    def badge_designer_field_label(self, path):
        return self._badge_path_label(path)


class ReportBadge(models.AbstractModel):
    _name = 'report.advanced_hr.report_badge'
    _description = 'ID Badge Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        # Read the badge as superuser; the employees are read as the user printing.
        template = self.env['advanced.hr.badge.template'].sudo().browse(data.get('badge_template_id')).exists()
        employees = self.env['hr.employee'].browse(docids)
        if not template:
            raise UserError(self.env._('This ID badge no longer exists.'))
        wrong = employees.filtered(lambda e: template.company_id and e.company_id != template.company_id)
        if wrong:
            raise UserError(self.env._(
                'The ID badge "%(badge)s" is only for %(company)s. It cannot be printed for %(employees)s.',
                badge=template.name, company=template.company_id.name, employees=', '.join(wrong.mapped('name'))))
        return {
            'doc_ids': docids,
            'doc_model': 'hr.employee',
            'docs': employees,
            'template': template,
            'badges': {employee.id: template._badge_render(employee) for employee in employees},
        }
