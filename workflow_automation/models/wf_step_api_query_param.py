# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WfStepApiQueryParam(models.Model):
    """A URL query-string parameter for a Workflow API Call step.

    Rows in this table are appended to the request URL as
    ``?key=value&key2=value2`` (encoded automatically by the ``requests``
    library).  They apply to **all** HTTP methods — GET, POST, PUT, PATCH,
    DELETE — mirroring the behaviour of the *Params* tab in Postman.

    Values support ``{{expression}}`` templates resolved at runtime against
    the trigger record and the current workflow variable context.

    Examples
    --------
    * ``page``  / ``{{variables.current_page}}``
    * ``filter`` / ``active``
    * ``record_id`` / ``{{record.id}}``
    * ``tenant`` / ``{{record.company_id.name}}``
    """

    _name = 'wf.step.api.query.param'
    _description = 'Workflow Step — API Query Parameter'
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
        string='Key',
        required=True,
        help='Query-string parameter name (e.g. page, filter, record_id).',
    )
    value = fields.Char(
        string='Value',
        help=(
            'Parameter value.  Supports {{expression}} templates:\n'
            '  {{record.id}}                 — trigger record field\n'
            '  {{record.partner_id.email}}   — related field (dot-path)\n'
            '  {{variables.my_var}}          — stored workflow variable'
        ),
    )
