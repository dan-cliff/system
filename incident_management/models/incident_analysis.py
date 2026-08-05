# -*- coding: utf-8 -*-
from odoo import fields, models


class IncidentReportAnalysis(models.Model):
    """Flattened SQL view that exposes one row per (incident, category) pair.

    This makes it possible to group by Category in graph/pivot views even
    though categories are stored as a Many2many on incident.report.
    Incidents with no category assigned appear once with type_id = False.
    """
    _name = 'incident.report.analysis'
    _description = 'Incident Report Analysis'
    _auto = False
    _rec_name = 'incident_id'
    _order = 'date_occurred desc'

    incident_id = fields.Many2one(
        'incident.report', string='Incident', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('assigned', 'Assigned'),
        ('under_investigation', 'Under Investigation'),
        ('corrective_actions', 'Corrective Actions'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', readonly=True)
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Severity', readonly=True)
    date_occurred = fields.Date('Date of Incident', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    responsible_manager_id = fields.Many2one(
        'res.users', string='Responsible Manager', readonly=True)
    type_id = fields.Many2one(
        'incident.type.tag', string='Category', readonly=True)
    person_type = fields.Selection([
        ('employee', 'Employee'),
        ('contractor', 'Contractor'),
        ('visitor', 'Visitor'),
        ('member_of_public', 'Member of Public'),
        ('other', 'Other'),
    ], string='Person Type', readonly=True)
    near_miss = fields.Boolean('Near Miss', readonly=True)
    incident_count = fields.Integer('# Incidents', readonly=True, aggregator='sum')

    def _query(self):
        return """
            SELECT
                row_number() OVER ()            AS id,
                ir.id                           AS incident_id,
                ir.state                        AS state,
                ir.severity                     AS severity,
                ir.date_occurred::date          AS date_occurred,
                ir.department_id                AS department_id,
                ir.responsible_manager_id       AS responsible_manager_id,
                ir.person_type                  AS person_type,
                ir.near_miss                    AS near_miss,
                it.id                           AS type_id,
                1                               AS incident_count
            FROM incident_report ir
            LEFT JOIN incident_report_type_rel rel ON rel.report_id = ir.id
            LEFT JOIN incident_type_tag        it  ON it.id = rel.type_id
        """

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS %s" % self._table)
        self.env.cr.execute(
            "CREATE VIEW %s AS (%s)" % (self._table, self._query())
        )
