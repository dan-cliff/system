import mimetypes
import threading

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import content_disposition, request

from ..lib.package_builder import read_package_file

# Recently built preview packages, keyed by (db, course id, last change). A
# preview loads index.html plus every asset, so the zip is built once per
# change instead of once per file.
_PREVIEW_CACHE = {}
_PREVIEW_LOCK = threading.Lock()
_PREVIEW_CACHE_SIZE = 6


class ScormAuthoringController(http.Controller):

    def _course(self, course_id):
        course = request.env['lms.scorm.course'].browse(course_id)
        try:
            course.check_access('read')
            course.ensure_one()
            course.name  # noqa: B018 - raises MissingError for deleted records
        except (AccessError, MissingError, ValueError):
            return None
        return course

    @staticmethod
    def _cache_key(course):
        stamps = [course.write_date, course.company_id.write_date] + course.slide_ids.mapped('write_date')
        return (request.env.cr.dbname, course.id, str(max(d for d in stamps if d)), len(course.slide_ids))

    @http.route('/scorm_authoring/<int:course_id>/preview/<path:path>', type='http', auth='user')
    def preview_file(self, course_id, path, **kwargs):
        """Serve the course from a package built in memory.

        No SCORM runtime is offered here, so the player runs in preview mode:
        nothing is saved to the LMS or to any learner's training record.
        """
        course = self._course(course_id)
        if not course:
            return request.not_found()
        key = self._cache_key(course)
        with _PREVIEW_LOCK:
            package = _PREVIEW_CACHE.get(key)
        if package is None:
            package = course._build_package(preview=True)
            with _PREVIEW_LOCK:
                for stale in [k for k in _PREVIEW_CACHE if k[:2] == key[:2]]:
                    _PREVIEW_CACHE.pop(stale, None)
                while len(_PREVIEW_CACHE) >= _PREVIEW_CACHE_SIZE:
                    _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))
                _PREVIEW_CACHE[key] = package
        data = read_package_file(package, path)
        if data is None:
            return request.not_found()
        mimetype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if path.endswith('.js'):
            mimetype = 'application/javascript'
        return request.make_response(data, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', str(len(data))),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @http.route('/scorm_authoring/<int:course_id>/download', type='http', auth='user')
    def download(self, course_id, **kwargs):
        course = self._course(course_id)
        if not course or course.state not in ('approved', 'published', 'superseded'):
            return request.not_found()
        package = course._build_package()
        filename = course._package_filename()
        return request.make_response(package, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Length', str(len(package))),
            ('Content-Disposition', content_disposition(filename)),
        ])
