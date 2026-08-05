# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApiAuthEndpoint(models.Model):
    _name = "api.auth.endpoint"
    _description = "API Auth Endpoint"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    route = fields.Selection(
        [
            ("login", "Login"),
            ("register", "Register"),
            ("reset_password", "Reset Password"),
            ("user_details", "User Details"),
        ],
        required=True,
    )
    endpoint_url = fields.Char(compute="_compute_endpoint_url", readonly=True)
    example_request = fields.Text(compute="_compute_example_request", readonly=True)
    max_failed_attempts = fields.Integer(
        default=5,
        help="Number of failed attempts allowed before cooldown is applied.",
    )
    failure_window_minutes = fields.Integer(
        default=15,
        help="Time window in minutes used to count failed attempts.",
    )
    cooldown_minutes = fields.Integer(
        default=15,
        help="Cooldown duration in minutes after limit is reached.",
    )

    _constraint_route_unique = models.Constraint(
        "unique(route)", "Route must be unique."
    )

    def _uses_cooldown(self):
        self.ensure_one()
        return self.route in ("login", "reset_password")

    @api.constrains("max_failed_attempts", "failure_window_minutes", "cooldown_minutes")
    def _check_cooldown_values(self):
        for record in self:
            if not record._uses_cooldown():
                continue
            if record.max_failed_attempts < 1:
                raise UserError(_("Max Failed Attempts must be at least 1."))
            if record.failure_window_minutes < 1:
                raise UserError(_("Failure Window must be at least 1 minute."))
            if record.cooldown_minutes < 1:
                raise UserError(_("Cooldown Minutes must be at least 1."))

    @api.depends("route")
    def _compute_endpoint_url(self):
        for record in self:
            if record.route == "login":
                record.endpoint_url = "/api/login"
            elif record.route == "register":
                record.endpoint_url = "/api/register"
            elif record.route == "reset_password":
                record.endpoint_url = "/api/password/reset"
            elif record.route == "user_details":
                record.endpoint_url = "/api/user/details"
            else:
                record.endpoint_url = False

    @api.depends("route")
    def _compute_example_request(self):
        for record in self:
            if record.route == "login":
                record.example_request = (
                    "Required: login, password\n"
                    "Optional: db (auto-picked if single database exists)\n"
                    "Example JSON:\n"
                    "{\n"
                    '  "db": "db_name",\n'
                    '  "login": "john@example.com",\n'
                    '  "password": "secret"\n'
                    "}"
                )
            elif record.route == "register":
                record.example_request = (
                    "Required: name, email, password\n"
                    "Optional: phone\n"
                    "Example JSON:\n"
                    "{\n"
                    '  "name": "John Doe",\n'
                    '  "email": "john@example.com",\n'
                    '  "password": "secret",\n'
                    '  "phone": "123456789"\n'
                    "}"
                )
            elif record.route == "reset_password":
                record.example_request = (
                    "Required: email\n"
                    "Example JSON:\n"
                    "{\n"
                    '  "email": "john@example.com"\n'
                    "}"
                )
            elif record.route == "user_details":
                record.example_request = (
                    "No JSON body required.\n"
                    "Requires authenticated session from /api/login.\n"
                    "Send Cookie: session_id=<session_id>"
                )
            else:
                record.example_request = False

    def unlink(self):
        if self.env.context.get("module_uninstall") or self.env.context.get(
            "uninstall_mode"
        ):
            return super().unlink()
        raise UserError(_("Auth endpoints cannot be deleted. Deactivate them instead."))
