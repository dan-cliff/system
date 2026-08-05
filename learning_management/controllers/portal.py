import base64
import io
import json
import logging
import mimetypes
import os
import zipfile

from odoo import http, fields, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_logger = logging.getLogger(__name__)


class LmsPortal(CustomerPortal):
    """Employee portal for Learning Management System."""

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        employee = self._get_current_employee()
        if 'training_count' in counters:
            if employee:
                values['training_count'] = request.env['lms.employee.record'].search_count([
                    ('employee_id', '=', employee.id),
                    ('state', 'in', ('not_started', 'in_progress', 'pending_upload', 'pending_verification')),
                ])
            else:
                values['training_count'] = 0
        if 'training_history_count' in counters:
            if employee:
                values['training_history_count'] = request.env['lms.employee.record'].search_count([
                    ('employee_id', '=', employee.id),
                    ('state', 'in', ('completed', 'expired')),
                ])
            else:
                values['training_history_count'] = 0
        return values

    def _get_current_employee(self):
        """Return the hr.employee record for the current user, or False."""
        return request.env['hr.employee'].search([
            ('user_id', '=', request.env.user.id),
            ('active', '=', True),
        ], limit=1)

    # ─── My Training Dashboard ───────────────────────────────────────────────

    @http.route('/my/training', type='http', auth='user', website=True)
    def my_training(self, filter='pending', **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        Record = request.env['lms.employee.record']
        Enrollment = request.env['lms.session.enrollment']

        # All records for stat tiles
        all_records = Record.search([('employee_id', '=', employee.id)])
        counts = {}
        for state in ('not_started', 'in_progress', 'pending_upload',
                      'pending_verification', 'completed', 'failed', 'expired'):
            counts[state] = sum(1 for r in all_records if r.state == state)
        counts['pending'] = sum(
            counts.get(s, 0)
            for s in ('not_started', 'in_progress', 'pending_upload', 'pending_verification')
        )

        # Filter records
        if filter == 'pending':
            records = all_records.filtered(
                lambda r: r.state in ('not_started', 'in_progress', 'pending_upload', 'pending_verification')
            )
        elif filter == 'completed':
            records = all_records.filtered(lambda r: r.state == 'completed')
        elif filter == 'open_sessions':
            records = request.env['lms.employee.record']
        else:  # 'all'
            records = all_records

        # Open sessions for self-enrolment
        open_sessions = request.env['lms.course.session']
        enrolled_session_ids = set()
        if filter == 'open_sessions':
            open_sessions = request.env['lms.course.session'].search([
                ('state', '=', 'open'),
                ('is_public', '=', True),
                ('available_seats', '>', 0),
            ])
            enrolled_session_ids = set(Enrollment.search([
                ('employee_id', '=', employee.id),
                ('state', 'not in', ('cancelled',)),
            ]).mapped('session_id').ids)

        values = {
            'employee': employee,
            'records': records,
            'counts': counts,
            'filter': filter,
            'open_sessions': open_sessions,
            'enrolled_session_ids': enrolled_session_ids,
            'page_name': 'training',
        }
        return request.render('learning_management.portal_my_training', values)

    # ─── Training History ────────────────────────────────────────────────────

    @http.route('/my/training/history', type='http', auth='user', website=True)
    def training_history(self, sort='completion_date desc', course_type=None, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        domain = [
            ('employee_id', '=', employee.id),
            ('state', 'in', ('completed', 'expired')),
        ]
        if course_type:
            domain.append(('course_type', '=', course_type))

        # Validate sort
        allowed_sorts = {
            'completion_date desc': 'completion_date desc',
            'completion_date asc': 'completion_date asc',
            'course_name': 'course_id',
            'expiry_date': 'expiry_date asc',
        }
        order = allowed_sorts.get(sort, 'completion_date desc')

        records = request.env['lms.employee.record'].search(domain, order=order)

        # Summary stats
        total = len(records)
        expiring_soon = records.filtered(
            lambda r: r.expiry_date and r.state == 'completed' and
            (r.expiry_date - fields.Date.today()).days <= 90 and
            (r.expiry_date - fields.Date.today()).days >= 0
        )
        expired_count = sum(1 for r in records if r.state == 'expired')

        values = {
            'employee': employee,
            'records': records,
            'total': total,
            'expiring_soon': expiring_soon,
            'expiring_soon_count': len(expiring_soon),
            'expired_count': expired_count,
            'sort': sort,
            'course_type': course_type or '',
            'page_name': 'training_history',
        }
        return request.render('learning_management.portal_training_history', values)

    # ─── Individual Training Record ──────────────────────────────────────────

    @http.route('/my/training/<int:record_id>', type='http', auth='user', website=True)
    def training_record(self, record_id, upload_ok=False, upload_error=None, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.not_found()

        # Auto-start
        if record.state == 'not_started':
            record.action_start()

        # Map error codes to human-readable messages
        _upload_errors = {
            'no_file':      'No file was selected. Please choose a file and try again.',
            'empty_file':   'The selected file appears to be empty. Please choose a different file.',
            'server_error': 'An error occurred while saving your file. Please try again, '
                            'or contact your training manager if the problem persists.',
        }

        # Fetch the most recent assessment for this training record (if any)
        assessment = False
        if record.course_id.assessment_template_id:
            assessment = request.env['lms.assessment'].search([
                ('employee_record_id', '=', record.id),
            ], order='id desc', limit=1)

        values = {
            'record': record,
            'employee': employee,
            'assessment': assessment,
            'page_name': 'training_detail',
            'upload_ok': bool(upload_ok),
            'upload_error': _upload_errors.get(upload_error, ''),
        }
        return request.render('learning_management.portal_training_record', values)

    # ─── Assessment: Start ───────────────────────────────────────────────────

    @http.route('/my/training/<int:record_id>/assessment/start', type='http',
                auth='user', website=True, methods=['POST'])
    def assessment_start(self, record_id, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record or not record.course_id.assessment_template_id:
            return request.not_found()

        # Re-use an existing draft/in-progress assessment; otherwise create fresh
        assessment = request.env['lms.assessment'].search([
            ('employee_record_id', '=', record.id),
            ('state', 'in', ('draft', 'in_progress')),
        ], order='id desc', limit=1)

        if not assessment:
            assessment = request.env['lms.assessment'].create({
                'template_id': record.course_id.assessment_template_id.id,
                'employee_record_id': record.id,
            })

        if assessment.state == 'draft':
            assessment.action_start()

        return request.redirect('/my/training/%d' % record_id)

    # ─── Assessment: Submit answers ──────────────────────────────────────────

    @http.route('/my/training/<int:record_id>/assessment/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def assessment_submit(self, record_id, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.not_found()

        assessment = request.env['lms.assessment'].search([
            ('employee_record_id', '=', record.id),
            ('state', '=', 'in_progress'),
        ], order='id desc', limit=1)
        if not assessment:
            return request.redirect('/my/training/%d' % record_id)

        # Persist each answer from the submitted form
        form = request.httprequest.form
        for answer in assessment.answer_ids:
            q_type = answer.question_type
            if q_type == 'multiple_choice':
                raw = form.get('answer_%d_option' % answer.id, '')
                try:
                    answer.write({'selected_option_id': int(raw)})
                except (ValueError, TypeError):
                    pass
            elif q_type == 'true_false':
                val = form.get('answer_%d_bool' % answer.id, '')
                if val in ('true', 'false'):
                    answer.write({'bool_answer': val})
            elif q_type == 'short_text':
                answer.write({'text_answer': form.get('answer_%d_text' % answer.id, '')})

        assessment.action_submit()
        return request.redirect('/my/training/%d' % record_id)

    # ─── Assessment: Retry ───────────────────────────────────────────────────

    @http.route('/my/training/<int:record_id>/assessment/retry', type='http',
                auth='user', website=True, methods=['POST'])
    def assessment_retry(self, record_id, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record or not record.course_id.assessment_template_id:
            return request.not_found()

        # Create a new assessment instance (preserving history of the failed one)
        assessment = request.env['lms.assessment'].create({
            'template_id': record.course_id.assessment_template_id.id,
            'employee_record_id': record.id,
        })
        assessment.action_start()
        return request.redirect('/my/training/%d' % record_id)

    # ─── Mark Complete (Google Slides / Document) ────────────────────────────

    @http.route('/my/training/<int:record_id>/complete', type='http', auth='user',
                website=True, methods=['POST'])
    def training_complete(self, record_id, confirm=None, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.not_found()

        if confirm and record.state not in ('completed',):
            # Server-side gate: Google Slides with slide_count set
            if (record.course_id.delivery_mode == 'google_slides'
                    and record.course_id.slide_count > 0
                    and record.slides_max_page < record.course_id.slide_count):
                # Redirect back; the template will keep the button disabled
                return request.redirect('/my/training/%d' % record_id)
            record._mark_completed()

        return request.redirect('/my/training/%d' % record_id)

    # ─── Google Slides progress tracking ─────────────────────────────────────

    @http.route('/my/training/<int:record_id>/slides/progress', type='http',
                auth='user', methods=['POST'], csrf=False)
    def slides_progress(self, record_id, page='1', **kwargs):
        """
        Save the furthest slide the employee has reached.
        Called via fetch() from lms_scorm.js on every Next click.
        Returns JSON: {max_page, slide_count, all_viewed}
        """
        employee = self._get_current_employee()
        if not employee:
            return request.make_response(
                json.dumps({'error': 'no_employee'}),
                headers=[('Content-Type', 'application/json')]
            )

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.make_response(
                json.dumps({'error': 'not_found'}),
                headers=[('Content-Type', 'application/json')]
            )

        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1

        if page > record.slides_max_page:
            record.write({'slides_max_page': page})

        slide_count = record.course_id.slide_count
        return request.make_response(
            json.dumps({
                'max_page': record.slides_max_page,
                'slide_count': slide_count,
                'all_viewed': slide_count > 0 and record.slides_max_page >= slide_count,
            }),
            headers=[('Content-Type', 'application/json')]
        )

    # ─── Document Upload (Licence / Qualification) ───────────────────────────

    @http.route('/my/training/<int:record_id>/upload', type='http', auth='user',
                website=True, methods=['POST'])
    def training_upload(self, record_id, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.not_found()

        # In Odoo 19, uploaded files are NOT in request.params / route kwargs —
        # they must be read directly from request.httprequest.files.
        upload_file = request.httprequest.files.get('upload_file')

        if not upload_file or not upload_file.filename:
            return request.redirect(
                '/my/training/%d?upload_error=no_file' % record_id
            )

        try:
            file_data = upload_file.read()
            if not file_data:
                return request.redirect(
                    '/my/training/%d?upload_error=empty_file' % record_id
                )

            # base64.b64encode returns bytes; decode to str for ir.attachment.datas
            attachment = request.env['ir.attachment'].sudo().create({
                'name': upload_file.filename,
                'datas': base64.b64encode(file_data).decode('ascii'),
                'res_model': 'lms.employee.record',
                'res_id': record.id,
                'mimetype': upload_file.content_type or 'application/octet-stream',
            })

            vals = {'attachment_ids': [(4, attachment.id)]}
            if record.state in ('not_started', 'pending_upload'):
                vals['state'] = 'pending_verification'
            if not record.start_date:
                vals['start_date'] = fields.Date.today()
            record.write(vals)

        except Exception as e:
            _logger.error('LMS upload error for record %s: %s', record_id, e)
            return request.redirect(
                '/my/training/%d?upload_error=server_error' % record_id
            )

        return request.redirect('/my/training/%d?upload_ok=1' % record_id)

    # ─── Open Sessions Page ──────────────────────────────────────────────────

    @http.route('/my/training/sessions', type='http', auth='user', website=True)
    def open_sessions(self, course_id=None, **kwargs):
        """Dedicated page listing all open sessions available for self-enrolment."""
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        domain = [
            ('state', '=', 'open'),
            ('is_public', '=', True),
            ('available_seats', '>', 0),
        ]
        if course_id:
            try:
                domain.append(('course_id', '=', int(course_id)))
            except (ValueError, TypeError):
                pass

        open_sessions = request.env['lms.course.session'].search(domain, order='date_start asc')

        enrolled_session_ids = set(
            request.env['lms.session.enrollment'].search([
                ('employee_id', '=', employee.id),
                ('state', 'not in', ('cancelled',)),
            ]).mapped('session_id').ids
        )

        # Distinct courses for filter dropdown
        available_courses = open_sessions.mapped('course_id')

        values = {
            'employee': employee,
            'open_sessions': open_sessions,
            'enrolled_session_ids': enrolled_session_ids,
            'available_courses': available_courses,
            'selected_course_id': int(course_id) if course_id else 0,
            'page_name': 'open_sessions',
        }
        return request.render('learning_management.portal_open_sessions', values)

    # ─── Self-Enrolment ──────────────────────────────────────────────────────

    @http.route('/my/training/session/enroll/<int:session_id>', type='http', auth='user',
                website=True, methods=['POST'])
    def session_enroll(self, session_id, **kwargs):
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/my/home')

        session = request.env['lms.course.session'].search([
            ('id', '=', session_id),
            ('state', '=', 'open'),
            ('is_public', '=', True),
        ], limit=1)
        if not session:
            return self._lms_flash(
                'error', 'Session Unavailable',
                'This session is no longer available for enrolment.'
            )

        # Check if already enrolled
        existing = request.env['lms.session.enrollment'].search([
            ('session_id', '=', session_id),
            ('employee_id', '=', employee.id),
            ('state', 'not in', ('cancelled',)),
        ], limit=1)
        if existing:
            return request.redirect('/my/training/sessions')

        # Check capacity
        if session.available_seats <= 0:
            return self._lms_flash(
                'warning', 'Session Full',
                'Sorry, this session is now full. Please check back for other sessions.'
            )

        # Determine if approval required
        needs_approval = session.requires_approval and bool(employee.parent_id)
        enrollment_state = 'pending_approval' if needs_approval else 'confirmed'

        request.env['lms.session.enrollment'].create({
            'session_id': session.id,
            'employee_id': employee.id,
            'enrolled_by': request.env.user.id,
            'is_self_enrolled': True,
            'approval_required': needs_approval,
            'state': enrollment_state,
        })

        if needs_approval:
            return self._lms_flash(
                'success', 'Enrolment Request Submitted',
                'Your enrolment request has been submitted to your manager for approval. '
                'You will be notified once it has been reviewed.'
            )
        return self._lms_flash(
            'success', 'Enrolment Confirmed',
            'You have been successfully enrolled in %s.' % session.name
        )

    def _lms_flash(self, msg_type, msg_title, msg_body):
        return request.render('learning_management.portal_lms_flash', {
            'msg_type': {'success': 'success', 'error': 'danger', 'warning': 'warning'}.get(msg_type, 'info'),
            'msg_title': msg_title,
            'msg_body': msg_body,
        })

    # ─── SCORM File Server ───────────────────────────────────────────────────

    @http.route('/lms/scorm/<int:record_id>/play', type='http', auth='user')
    def scorm_play(self, record_id, **kwargs):
        """Render the SCORM wrapper page (loads inside portal iframe)."""
        employee = self._get_current_employee()
        if not employee:
            return request.redirect('/web/login')

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record or not record.course_id.scorm_package_id:
            return request.not_found()

        # Determine launch file
        launch_file = record.course_id.scorm_launch_file
        if not launch_file:
            launch_file = self._detect_scorm_launch(record.course_id.scorm_package_id)

        launch_url = '/lms/scorm/%d/file/%s' % (record_id, launch_file or 'index.html')

        values = {
            'record_id': record_id,
            'course_id': record.course_id.id,
            'passing_score': record.course_id.passing_score or 80,
            'launch_url': launch_url,
        }
        return request.render('learning_management.portal_scorm_wrapper', values)

    def _detect_scorm_launch(self, scorm_data):
        """Try to detect the SCORM launch file from the ZIP manifest.

        scorm_data is the base64-encoded content of the SCORM ZIP, as returned
        directly by the Binary field (lms.course.scorm_package_id).
        """
        try:
            zip_data = base64.b64decode(scorm_data)
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                names = zf.namelist()
                # Try imsmanifest.xml
                if 'imsmanifest.xml' in names:
                    manifest_data = zf.read('imsmanifest.xml').decode('utf-8', errors='ignore')
                    # Simple string search for launch href
                    import re
                    match = re.search(r'<resource[^>]+href="([^"]+)"', manifest_data, re.IGNORECASE)
                    if match:
                        return match.group(1)
                # Fallbacks
                for candidate in ('index.html', 'index.htm', 'story.html',
                                  'launch.html', 'default.html'):
                    if candidate in names:
                        return candidate
                # Find any HTML file
                html_files = [n for n in names if n.lower().endswith('.html') and '/' not in n]
                if html_files:
                    return html_files[0]
        except Exception as e:
            _logger.warning('Could not detect SCORM launch file: %s', e)
        return 'index.html'

    @http.route('/lms/scorm/<int:record_id>/file/<path:filepath>', type='http', auth='user')
    def scorm_file(self, record_id, filepath, **kwargs):
        """Serve a file from inside the SCORM ZIP package."""
        employee = self._get_current_employee()
        if not employee:
            return request.not_found()

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record or not record.course_id.scorm_package_id:
            return request.not_found()

        try:
            zip_data = base64.b64decode(record.course_id.scorm_package_id)
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                # Normalise path separators
                clean_path = filepath.replace('\\', '/').lstrip('/')
                if clean_path not in zf.namelist():
                    return request.not_found()
                file_data = zf.read(clean_path)
        except Exception as e:
            _logger.error('SCORM file serve error: %s', e)
            return request.not_found()

        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            mime_type = 'application/octet-stream'

        headers = [
            ('Content-Type', mime_type),
            ('Content-Length', len(file_data)),
            ('Cache-Control', 'private, max-age=300'),
        ]
        return request.make_response(file_data, headers=headers)

    @http.route('/lms/scorm/<int:record_id>/commit', type='http', auth='user',
                methods=['POST'], csrf=False)
    def scorm_commit(self, record_id, **kwargs):
        """Receive SCORM runtime data from the JavaScript API."""
        employee = self._get_current_employee()
        if not employee:
            return request.make_response('{}', headers=[('Content-Type', 'application/json')])

        record = request.env['lms.employee.record'].search([
            ('id', '=', record_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        if not record:
            return request.make_response('{}', headers=[('Content-Type', 'application/json')])

        try:
            payload = json.loads(request.httprequest.data or '{}')
        except Exception:
            payload = {}

        action = payload.get('action', '')
        cmi = payload.get('cmi', {})

        # Extract key SCORM values
        lesson_status = (
            cmi.get('cmi.core.lesson_status') or
            cmi.get('cmi.completion_status') or
            ''
        ).lower()
        score_raw = cmi.get('cmi.core.score.raw') or cmi.get('cmi.score.raw') or 0
        try:
            score_raw = float(score_raw)
        except (ValueError, TypeError):
            score_raw = 0.0

        vals = {
            'scorm_data': json.dumps(cmi),
            'scorm_completion_status': lesson_status,
        }
        if score_raw:
            vals['score'] = score_raw

        # Auto-complete on passed/completed status
        if lesson_status in ('passed', 'completed'):
            passing = record.course_id.passing_score or 80
            passed = score_raw >= passing if score_raw else True
            vals['passed'] = passed
            if passed and record.state not in ('completed',):
                record._mark_completed()
        elif lesson_status in ('failed',):
            vals['state'] = 'failed'
            vals['passed'] = False
        elif action in ('initialize',) and record.state == 'not_started':
            vals['state'] = 'in_progress'
            vals['start_date'] = fields.Date.today()

        record.write(vals)

        return request.make_response(
            json.dumps({'status': 'ok'}),
            headers=[('Content-Type', 'application/json')]
        )
