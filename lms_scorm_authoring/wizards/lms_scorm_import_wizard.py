import base64
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib.pptx_converter import PptxConverter, PresentationError, google_slides_export_url

_logger = logging.getLogger(__name__)

GOOGLE_MAX_BYTES = 200 * 1024 * 1024


class LmsScormImportWizard(models.TransientModel):
    _name = 'lms.scorm.import.wizard'
    _description = 'Import a Presentation into a SCORM Course'

    course_id = fields.Many2one('lms.scorm.course', string='Course', required=True, ondelete='cascade')
    source = fields.Selection([
        ('file', 'PowerPoint / Google Slides file (.pptx)'),
        ('google', 'Google Slides link'),
    ], string='Import From', default='file', required=True)
    file = fields.Binary(string='Presentation File')
    filename = fields.Char(string='File Name')
    google_url = fields.Char(
        string='Google Slides Link',
        help='Share the presentation with "Anyone with the link" (Viewer) and paste the link.')
    mode = fields.Selection([
        ('append', 'Add after the existing slides'),
        ('replace', 'Replace all existing slides'),
    ], string='Slides', default='append', required=True)
    has_slides = fields.Boolean(compute='_compute_has_slides')
    state = fields.Selection([('upload', 'Upload'), ('done', 'Done')], default='upload')
    result_summary = fields.Text(string='Result', readonly=True)
    result_warnings = fields.Text(string='Things to Check', readonly=True)

    @api.depends('course_id')
    def _compute_has_slides(self):
        for wizard in self:
            wizard.has_slides = bool(wizard.course_id.slide_ids)

    def _download_google(self):
        export_url = google_slides_export_url(self.google_url)
        if not export_url:
            raise UserError(_(
                'That is not a Google Slides link. Open the presentation and copy the link from '
                'the address bar (it contains docs.google.com/presentation/d/...).'))
        try:
            response = requests.get(export_url, timeout=90, stream=True, allow_redirects=True)
        except requests.RequestException as error:
            raise UserError(_('Google Slides could not be reached: %s', error))
        content_type = response.headers.get('Content-Type', '')
        if response.status_code != 200 or 'text/html' in content_type:
            raise UserError(_(
                'Google did not share the presentation. In Google Slides choose Share > General '
                'access > "Anyone with the link" (Viewer), or download it as .pptx '
                '(File > Download > Microsoft PowerPoint) and upload the file instead.'))
        chunks = []
        size = 0
        for chunk in response.iter_content(1024 * 256):
            size += len(chunk)
            if size > GOOGLE_MAX_BYTES:
                raise UserError(_('The presentation is too large to import.'))
            chunks.append(chunk)
        return b''.join(chunks)

    def action_import(self):
        self.ensure_one()
        course = self.course_id
        course.check_access('write')
        if course.state != 'draft':
            raise UserError(_('Only draft versions can be changed. Create a new version first.'))
        if self.source == 'google':
            data = self._download_google()
            name = _('Google Slides')
        else:
            if not self.file:
                raise UserError(_('Choose the presentation file to import.'))
            name = self.filename or 'presentation.pptx'
            if name.lower().endswith(('.ppt', '.pps', '.pot')):
                raise UserError(_(
                    'Old-style PowerPoint files (%s) cannot be converted. Open the file in '
                    'PowerPoint and save it as .pptx first.', name.rsplit('.', 1)[-1]))
            if name.lower().endswith(('.key', '.odp', '.pdf')):
                raise UserError(_(
                    'Only PowerPoint (.pptx) files can be converted. Export the presentation to '
                    '.pptx first.'))
            data = base64.b64decode(self.file)

        converter = PptxConverter(data, target_width=1280)
        try:
            converter.validate()
            result = converter.convert()
        except PresentationError as error:
            raise UserError(str(error))
        except Exception:
            _logger.exception('Presentation conversion failed')
            raise UserError(_(
                'The presentation could not be converted. Check it opens in PowerPoint, save it '
                'again as .pptx and retry.'))
        if not result['slides']:
            raise UserError(_('No visible slides were found in the presentation.'))

        # Store pictures and media as attachments of the course
        Attachment = self.env['ir.attachment']
        attachment_ids = {}
        for key, media in result['media'].items():
            attachment = Attachment.create({
                'name': media['name'],
                'raw': media['data'],
                'mimetype': media['mimetype'],
                'res_model': 'lms.scorm.course',
                'res_id': course.id,
            })
            attachment_ids[key] = attachment.id

        Slide = self.env['lms.scorm.slide']
        if self.mode == 'replace' and course.slide_ids:
            course.slide_ids.unlink()
        if not course.slide_ids:
            course.write({'slide_width': result['width'], 'slide_height': result['height']})
        x_scale = course.slide_width / result['width'] if result['width'] else 1
        y_scale = course.slide_height / result['height'] if result['height'] else 1
        if abs(x_scale - y_scale) > 0.02:
            result['warnings'].append(_(
                'The presentation is %(pw)sx%(ph)s but the course slides are %(cw)sx%(ch)s, so the '
                'imported slides were stretched to fit. Check pictures and shapes.',
                pw=result['width'], ph=result['height'], cw=course.slide_width, ch=course.slide_height))
        sequence = max(course.slide_ids.mapped('sequence') or [0])
        vals_list = []
        for slide in result['slides']:
            sequence += 1
            elements = []
            for element in slide['elements']:
                props = element.get('props', {})
                media_key = props.pop('media', None)
                if media_key:
                    if media_key not in attachment_ids:
                        continue
                    props['attachment_id'] = attachment_ids[media_key]
                if x_scale != 1 or y_scale != 1:
                    element['x'] = round(element['x'] * x_scale)
                    element['w'] = round(element['w'] * x_scale)
                    element['y'] = round(element['y'] * y_scale)
                    element['h'] = round(element['h'] * y_scale)
                elements.append(element)
            background = slide['background_color']
            if slide.get('background_css') and not background:
                # Gradients: keep it as a full-slide shape behind everything
                elements.insert(0, {
                    'id': 'bg%d' % sequence, 'type': 'shape', 'x': 0, 'y': 0,
                    'w': course.slide_width, 'h': course.slide_height, 'z': 0, 'rotation': 0,
                    'required': False, 'props': {'shape': 'rect'},
                    'style': {'background': slide['background_css']},
                })
            vals_list.append({
                'course_id': course.id,
                'sequence': sequence,
                'name': slide['name'][:200],
                'notes': slide['notes'] or False,
                'background_color': background or False,
                'background_attachment_id': attachment_ids.get(slide['background_media']) or False,
                'gate_require_interactions': True,
                'elements_json': json.dumps(elements),
            })
        Slide.create(vals_list)

        summary = _('%(slides)s slide(s) and %(media)s picture/media file(s) imported from %(name)s.',
                    slides=len(vals_list), media=len(attachment_ids), name=name)
        course.message_post(body=summary)
        self.write({
            'state': 'done',
            'result_summary': summary,
            'result_warnings': '\n'.join(result['warnings']) or False,
            'file': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Import Presentation'),
        }

    def action_open_editor(self):
        self.ensure_one()
        return self.course_id.action_open_editor()
