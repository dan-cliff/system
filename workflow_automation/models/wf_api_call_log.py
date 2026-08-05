# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class WfApiCallLog(models.Model):
    """Central log of every outbound API call made through the Workflow Engine.

    Each record captures the full request (headers, body) and response
    (status code, headers, body) along with timing and outcome so that
    integrations can be audited and debugged.

    The ``trigger_model_id`` / ``trigger_res_id`` pair identifies the Odoo
    record that initiated the call.  These fields are intentionally
    technology-neutral — any future model that makes an outbound API call
    can write a log entry here without depending on ``wf.service.platform``.
    """

    _name = 'wf.api.call.log'
    _description = 'API Call Log'
    _order = 'called_at desc, id desc'

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #

    name = fields.Char(
        string='Call Name',
        required=True,
        default='API Call',
        help='Short human-readable label for this call (e.g. "Authentication", "Fetch Orders").',
    )

    # ------------------------------------------------------------------ #
    # Source: which service/platform was called                           #
    # ------------------------------------------------------------------ #

    service_platform_id = fields.Many2one(
        'wf.service.platform',
        string='Service / Platform',
        ondelete='set null',
        index=True,
        help='The service or platform configuration used for this call (if applicable).',
    )

    # ------------------------------------------------------------------ #
    # Source: which Odoo model/record triggered the call                  #
    # ------------------------------------------------------------------ #

    trigger_model_id = fields.Many2one(
        'ir.model',
        string='Source Model',
        ondelete='set null',
        index=True,
        help='The Odoo model whose record initiated this API call.',
    )
    trigger_res_id = fields.Integer(
        string='Source Record ID',
        index=True,
        help='ID of the specific record that triggered this API call.',
    )
    trigger_record_name = fields.Char(
        string='Source Record',
        help='Human-readable display name of the record that triggered this call '
             '(populated automatically when trigger_model_id and trigger_res_id are set).',
    )

    # ------------------------------------------------------------------ #
    # Request details                                                      #
    # ------------------------------------------------------------------ #

    endpoint = fields.Char(
        string='Endpoint URL',
        required=True,
    )
    http_method = fields.Selection(
        selection=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('PATCH', 'PATCH'),
            ('DELETE', 'DELETE'),
        ],
        string='HTTP Method',
        default='POST',
        required=True,
    )
    request_headers = fields.Text(
        string='Request Headers',
        help='HTTP request headers as formatted JSON (sensitive values are redacted).',
    )
    request_body = fields.Text(
        string='Request Body',
        help='HTTP request body as formatted JSON (sensitive values are redacted).',
    )

    # ------------------------------------------------------------------ #
    # Response details                                                     #
    # ------------------------------------------------------------------ #

    response_status_code = fields.Integer(
        string='HTTP Status Code',
    )
    response_headers = fields.Text(
        string='Response Headers',
        help='HTTP response headers as formatted JSON.',
    )
    response_body = fields.Text(
        string='Response Body',
        help='Raw HTTP response body (JSON or plain text).',
    )

    # ------------------------------------------------------------------ #
    # Outcome                                                              #
    # ------------------------------------------------------------------ #

    state = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('error', 'Error'),
        ],
        string='State',
        required=True,
        default='success',
    )
    error_message = fields.Text(
        string='Error Message',
        help='Exception or error description if the call failed.',
    )
    duration_ms = fields.Integer(
        string='Duration (ms)',
        help='Round-trip time from request send to response received, in milliseconds.',
    )
    called_at = fields.Datetime(
        string='Called At',
        default=fields.Datetime.now,
        readonly=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @api.model
    def _create_log(
        self,
        name,
        endpoint,
        http_method='POST',
        request_headers=None,
        request_body=None,
        response_status_code=None,
        response_headers=None,
        response_body=None,
        state='success',
        error_message=None,
        duration_ms=None,
        service_platform_id=None,
        trigger_model=None,
        trigger_res_id=None,
        trigger_record_name=None,
    ):
        """Convenience factory for creating a log entry.

        Parameters
        ----------
        name : str
            Short label for the call (e.g. ``'Authentication'``).
        endpoint : str
            The URL that was called.
        http_method : str
            HTTP verb — one of ``GET``, ``POST``, ``PUT``, ``PATCH``, ``DELETE``.
        request_headers : str | None
            Formatted JSON string of request headers.  Sensitive headers
            (``Authorization``, ``X-API-Key``) should be redacted by the
            caller before passing.
        request_body : str | None
            Formatted JSON string of the request payload.
        response_status_code : int | None
            HTTP response status code.
        response_headers : str | None
            Formatted JSON string of the response headers.
        response_body : str | None
            Raw response body text.
        state : str
            ``'success'`` or ``'error'``.
        error_message : str | None
            Exception / error description when ``state == 'error'``.
        duration_ms : int | None
            Round-trip duration in milliseconds.
        service_platform_id : int | None
            ID of the ``wf.service.platform`` record (if applicable).
        trigger_model : str | None
            Technical model name of the Odoo record that triggered the call
            (e.g. ``'wf.automation'``).
        trigger_res_id : int | None
            ID of the triggering record.
        trigger_record_name : str | None
            Human-readable display name of the triggering record.

        Returns
        -------
        wf.api.call.log
            The newly created log record.
        """
        vals = {
            'name': name or 'API Call',
            'endpoint': endpoint,
            'http_method': http_method,
            'request_headers': request_headers,
            'request_body': request_body,
            'response_status_code': response_status_code,
            'response_headers': response_headers,
            'response_body': response_body,
            'state': state,
            'error_message': error_message,
            'duration_ms': duration_ms,
            'service_platform_id': service_platform_id,
            'trigger_record_name': trigger_record_name,
        }

        if trigger_model:
            model_rec = self.env['ir.model']._get(trigger_model)
            if model_rec:
                vals['trigger_model_id'] = model_rec.id
            if trigger_res_id:
                vals['trigger_res_id'] = trigger_res_id
                # Auto-resolve display name if not provided
                if not trigger_record_name and model_rec:
                    try:
                        Model = self.env.get(trigger_model)
                        if Model:
                            rec = Model.sudo().browse(trigger_res_id)
                            if rec.exists():
                                vals['trigger_record_name'] = rec.display_name
                    except Exception:
                        pass

        try:
            return self.sudo().create(vals)
        except Exception:
            _logger.exception(
                'wf.api.call.log — failed to create log entry for call to %s', endpoint
            )
            return self.browse()
