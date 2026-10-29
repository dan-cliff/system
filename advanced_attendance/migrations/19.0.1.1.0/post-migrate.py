"""On Site 1.1 adds extra hours (overtime).

Databases that installed On Site 1.0 get Attendances' overtime rulesets (when
it is still installed) and the extra hours of their existing attendances.
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.advanced_attendance.hooks import _Importer

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False, 'tracking_disable': True,
                                             'onsite_no_alerts': True})
    importer = _Importer(env)
    if 'hr.attendance.overtime.ruleset' in env:
        importer.import_rulesets()
    Attendance = env['advanced.attendance']
    employees = Attendance.search([('check_out', '!=', False)]).employee_id
    for employee in employees:
        Attendance.search([('employee_id', '=', employee.id), ('check_out', '!=', False)])._update_overtime()
    if 'hr.attendance.overtime.line' in env:
        importer.import_overtime_status()
    _logger.info('On Site: worked out extra hours for %s employees', len(employees))
