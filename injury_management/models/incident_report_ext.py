from markupsafe import Markup
from odoo import api, fields, models, _


class IncidentReportExt(models.Model):
    """Extends incident.report to support RTW case auto-creation."""
    _inherit = 'incident.report'

    rtw_case_ids = fields.One2many(
        'injury.rtw.case', 'incident_id', string='RTW Cases')
    rtw_case_count = fields.Integer(
        'RTW Case Count', compute='_compute_rtw_case_count')

    def _compute_rtw_case_count(self):
        for rec in self:
            rec.rtw_case_count = len(rec.rtw_case_ids)

    def action_view_rtw_cases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return to Work Cases'),
            'res_model': 'injury.rtw.case',
            'view_mode': 'list,form',
            'domain': [('incident_id', '=', self.id)],
            'context': {'default_incident_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_auto_create_rtw()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'injury_lost_time' in vals or 'injury_restricted_duties' in vals:
            self._check_auto_create_rtw()
        return res

    def _check_auto_create_rtw(self):
        """Auto-create RTW case when integration is enabled and LTI/restricted duties is set."""
        integrate = self.env['ir.config_parameter'].sudo().get_param(
            'injury_management.integrate_rtw', False)
        if not integrate:
            return
        for rec in self:
            if (rec.injury_lost_time or rec.injury_restricted_duties) and not rec.rtw_case_ids:
                rec._auto_create_rtw_case()

    def _auto_create_rtw_case(self):
        """Create an RTW case from this incident and post an HTML chatter note."""
        # Require an employee to be set — RTW case cannot be created without one
        if not self.employee_id:
            return

        # Map injury type from incident categories
        if self.is_injury:
            injury_type = 'workplace'
        elif self.is_illness:
            injury_type = 'illness'
        else:
            injury_type = 'workplace'

        calendar = self.employee_id.resource_calendar_id
        vals = {
            'incident_id': self.id,
            'employee_id': self.employee_id.id,
            'injury_date': self.date_occurred.date() if self.date_occurred else fields.Date.today(),
            'injury_type': injury_type,
            'pre_injury_hours': calendar.hours_per_week if calendar else 0.0,
        }
        if self.description:
            vals['injury_description'] = self.description
        if self.injury_body_parts_display:
            vals['body_part_affected'] = self.injury_body_parts_display
        if self.responsible_manager_id:
            vals['case_manager_id'] = self.responsible_manager_id.id

        rtw_case = self.env['injury.rtw.case'].sudo().create(vals)

        # Build human-readable reason
        reasons = []
        if self.injury_lost_time:
            reasons.append(_('Lost Time Injury (LTI)'))
        if self.injury_restricted_duties:
            reasons.append(_('Restricted / Modified Duties'))
        reason_html = ' and '.join(
            f'<strong>{r}</strong>' for r in reasons)

        self.message_post(
            body=Markup(
                '<p><strong>Return to Work Case Automatically Created</strong></p>'
                '<p>A Return to Work case {link} has been automatically created '
                'because this incident has been flagged as: {reason}.</p>'
                '<p>The case has been pre-populated with available details from '
                'this incident report. Please open the RTW case to review and '
                'complete any remaining information.</p>'
            ).format(
                link=rtw_case._get_html_link(),
                reason=Markup(reason_html),
            ),
            subtype_xmlid='mail.mt_note',
        )
