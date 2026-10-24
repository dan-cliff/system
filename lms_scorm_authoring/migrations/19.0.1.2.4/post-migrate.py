"""Rebuild the packages of LMS courses made from SCORM courses, so they get
the current player (it leaves full screen when Finish is pressed)."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    courses = env['lms.course'].with_context(active_test=False).search([
        ('scorm_course_id', '!=', False), ('scorm_course_id.state', '=', 'published'),
    ])
    for course in courses:
        try:
            with cr.savepoint():
                course.action_refresh_scorm_package()
        except Exception:
            _logger.exception('Could not rebuild the SCORM package of LMS course %s', course.id)
