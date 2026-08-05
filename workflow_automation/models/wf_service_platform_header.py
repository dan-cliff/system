# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WfServicePlatformHeader(models.Model):
    """A single HTTP request header to include on every outbound API call
    made through the parent ``wf.service.platform`` record.

    The rows are merged on top of the default headers that ``_authenticate``
    always sends (``Content-Type: application/json``, ``Accept: application/json``),
    so they can add new headers *or* override the defaults.
    """

    _name = 'wf.service.platform.header'
    _description = 'Service Platform — Request Header'
    _order = 'sequence, id'

    platform_id = fields.Many2one(
        'wf.service.platform',
        string='Platform',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(
        string='Header Name',
        required=True,
        help='HTTP header name (e.g. Accept, X-Tenant-ID, Authorization).',
    )
    value = fields.Char(
        string='Value',
        required=True,
        help='Header value.  Use {{username}}, {{password}}, {{client_id}}, '
             'or {{client_secret}} to inject the stored credential values at '
             'request time.',
    )
