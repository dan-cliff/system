# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WfStepApiHeader(models.Model):
    """A custom HTTP request header for a Workflow API Call step.

    Header values support ``{{expression}}`` templates evaluated in the
    standard workflow step context, giving access to ``record`` fields,
    ``variables`` from earlier steps, and the standard safe_eval helpers.

    Examples
    --------
    * ``{{record.company_id.name}}``         — trigger record field
    * ``{{record.partner_id.vat}}``          — related field (dot-path)
    * ``{{variables.auth_token}}``           — variable from a previous step
    """

    _name = 'wf.step.api.header'
    _description = 'Workflow Step — API Request Header'
    _order = 'sequence, id'

    step_id = fields.Many2one(
        'wf.step',
        string='Step',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(
        string='Header Name',
        required=True,
        help='HTTP header name (e.g. X-Tenant-ID, X-Correlation-ID).',
    )
    value = fields.Char(
        string='Value',
        help=(
            'Header value.  Supports {{expression}} templates:\n'
            '  {{record.name}}               — trigger record field\n'
            '  {{record.partner_id.email}}   — related field (dot-path)\n'
            '  {{variables.my_var}}          — stored workflow variable'
        ),
    )
