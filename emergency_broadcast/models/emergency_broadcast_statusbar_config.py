import re

from odoo import api, fields, models
from odoo.tools import html2plaintext


class EmergencyBroadcastStatusbarConfig(models.Model):
    """
    Configure an optional top-of-page banner to display whenever there is a
    Sent broadcast record with the given status.
    """
    _name = 'emergency.broadcast.statusbar.config'
    _description = 'Emergency Broadcast Statusbar Configuration'
    _order = 'status_id'
    _rec_name = 'status_id'

    status_id = fields.Many2one(
        'emergency.broadcast.status', 'Status', required=True, ondelete='cascade')
    show_banner = fields.Boolean('Show Banner', default=True)
    banner_type = fields.Selection([
        ('critical', 'Critical'),
        ('error', 'Error'),
        ('info', 'Information'),
        ('success', 'Success'),
    ], string='Banner Type', required=True, default='info')
    banner_color = fields.Char(
        'Custom Colour',
        help='Optional hex colour override, e.g. #FF0000.  Leave blank to use the Banner Type default colour.')
    banner_icon = fields.Char(
        'Icon Class', default='fa-exclamation-triangle',
        help='FontAwesome icon class, e.g. fa-exclamation-triangle, fa-info-circle, fa-check-circle.')
    banner_message_template = fields.Char(
        'Message Template',
        default='{{name}}',
        help=(
            'Template for the banner message.  Use {{field}} placeholders with fields from the broadcast record.\n'
            'Available: {{name}}, {{status_id.name}}, {{priority_label}}, {{sent_date}}, {{message_plain}}'
        ),
    )

    @api.model
    def get_active_banners(self):
        """
        Return a list of banner dicts for all statuses that have show_banner=True
        and at least one Sent broadcast.
        Called from the frontend JS on each page load.
        """
        configs = self.sudo().search([('show_banner', '=', True)])
        # Respect multi-company: only show banners for the user's active companies.
        # We use sudo() to bypass record rules, so the company filter is explicit.
        user_company_ids = self.env.companies.ids
        banners = []
        for cfg in configs:
            broadcast = self.env['emergency.broadcast'].sudo().search([
                ('status_id', '=', cfg.status_id.id),
                ('state', '=', 'sent'),
                ('company_id', 'in', user_company_ids),
            ], limit=1, order='sent_date desc')
            if not broadcast:
                continue
            banners.append({
                'id': broadcast.id,
                'name': broadcast.name,
                'message': cfg._render_banner_message(broadcast),
                'banner_type': cfg.banner_type,
                'banner_color': cfg.banner_color or '',
                'banner_icon': cfg.banner_icon or 'fa-exclamation-triangle',
                'config_id': cfg.id,
            })
        return banners

    def _render_banner_message(self, broadcast):
        """Substitute {{field}} placeholders with values from the broadcast record."""
        template = self.banner_message_template or '{{name}}'
        priority_map = dict(self.env['emergency.broadcast']._fields['priority'].selection)

        replacements = {
            '{{name}}': broadcast.name or '',
            '{{status_id.name}}': broadcast.status_id.name or '',
            '{{priority_label}}': priority_map.get(broadcast.priority, broadcast.priority or ''),
            '{{sent_date}}': (
                fields.Datetime.to_string(broadcast.sent_date) if broadcast.sent_date else ''
            ),
            '{{message_plain}}': (
                html2plaintext(broadcast.message_body)[:200] if broadcast.message_body else ''
            ),
        }
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        # Remove any un-replaced placeholders
        result = re.sub(r'\{\{[^}]+\}\}', '', result)
        return result
