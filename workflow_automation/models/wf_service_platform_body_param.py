# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

# Credential fields available for selection — displayed in the UI and
# resolved to the actual stored value at request time.
CREDENTIAL_FIELDS = [
    ('username',      'Username'),
    ('password',      'Password'),
    ('client_id',     'Client ID'),
    ('client_secret', 'Client Secret'),
]


class WfServicePlatformBodyParam(models.Model):
    """A single key/value pair that contributes to the JSON request body
    sent with every authentication call for the parent
    ``wf.service.platform`` record.

    When a ``Custom Request Body (JSON)`` override is *not* set, these rows
    are used to build the body dict in sequence order.  Each param can carry
    a plain static value *or* reference one of the stored credential fields
    so secrets never need to be typed into the JSON editor.

    Priority (in ``_authenticate``):

    1. JSON override field (``auth_request_body``) — if non-empty, these rows
       are ignored but ``{{credential}}`` placeholders in the override text
       are still resolved.
    2. This table — if rows exist, the body is built from them.
    3. Default body for the selected auth type.
    """

    _name = 'wf.service.platform.body.param'
    _description = 'Service Platform — Body Parameter'
    _order = 'sequence, id'

    platform_id = fields.Many2one(
        'wf.service.platform',
        string='Platform',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)

    key = fields.Char(
        string='Key',
        required=True,
        help='JSON key name (e.g. grant_type, scope, audience).',
    )

    value_type = fields.Selection(
        selection=[
            ('static',     'Static Value'),
            ('credential', 'Credential Field'),
        ],
        string='Value Type',
        required=True,
        default='static',
    )

    static_value = fields.Char(
        string='Value',
        help='Plain text value to include for this key.',
    )

    credential_field = fields.Selection(
        selection=CREDENTIAL_FIELDS,
        string='Credential Field',
        help='The stored credential field whose value will be resolved and '
             'injected at request time.  The actual value is never stored '
             'here — it is read directly from the platform record.',
    )

    # ------------------------------------------------------------------ #
    # Computed display — shown in the list column                         #
    # ------------------------------------------------------------------ #

    value_preview = fields.Char(
        string='Value / Field',
        compute='_compute_value_preview',
        store=False,
    )

    @api.depends('value_type', 'static_value', 'credential_field')
    def _compute_value_preview(self):
        label_map = dict(CREDENTIAL_FIELDS)
        for rec in self:
            if rec.value_type == 'static':
                rec.value_preview = rec.static_value or ''
            else:
                rec.value_preview = (
                    '{{%s}}' % label_map.get(rec.credential_field, rec.credential_field or '')
                )

    # ------------------------------------------------------------------ #
    # Runtime resolution                                                   #
    # ------------------------------------------------------------------ #

    def resolve_value(self):
        """Return the actual string value for this parameter.

        For ``static`` rows this is simply ``static_value``.
        For ``credential`` rows the value is read from the parent platform
        record so that secrets are never stored in this table.
        """
        self.ensure_one()
        if self.value_type == 'credential':
            return getattr(self.platform_id, self.credential_field or '') or ''
        return self.static_value or ''
