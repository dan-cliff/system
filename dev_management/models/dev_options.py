"""Option lists of the Development app, managed under Configuration (CLAUDE.md > Choice fields)."""
from odoo import fields, models


class DevTicketType(models.Model):
    _name = 'dev.ticket.type'
    _description = 'Ticket Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    icon = fields.Char(help='Font Awesome icon shown on tickets of this type, e.g. fa-bug.')
    branch_prefix = fields.Char(
        default='feature',
        help='Start of the names of the GitHub branches created for tickets of this type, e.g. '
             '"bugfix" gives bugfix/DEV-00012-short-summary.')
    description = fields.Text()


class DevPriority(models.Model):
    _name = 'dev.priority'
    _description = 'Ticket Priority'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10, help='Lower comes first: put the most urgent priority at the top.')
    active = fields.Boolean(default=True)
    color = fields.Integer('Color')
    icon = fields.Char(help='Font Awesome icon shown with this priority, e.g. fa-angle-double-up.')


class DevTicketStage(models.Model):
    _name = 'dev.ticket.stage'
    _description = 'Ticket Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean('Folded in Board')
    is_closed = fields.Boolean(
        'Closing Stage', help='Tickets in this stage are finished: they count as done in releases and features.')
    description = fields.Text()


class DevFeatureStage(models.Model):
    _name = 'dev.feature.stage'
    _description = 'Feature Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean('Folded in Board')
    is_closed = fields.Boolean('Closing Stage', help='Features in this stage are finished (released or parked).')
    description = fields.Text()


class DevLinkType(models.Model):
    _name = 'dev.link.type'
    _description = 'Ticket Link Type'
    _order = 'sequence, id'

    name = fields.Char('Outward Description', required=True, translate=True,
                       help='How the ticket that holds the link relates to the other one, e.g. "blocks".')
    inverse_name = fields.Char('Inward Description', required=True, translate=True,
                               help='How the other ticket relates back, e.g. "is blocked by".')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_blocking = fields.Boolean(
        'Blocks Work', help='The linked ticket is blocked until the ticket holding the link is closed.')


class DevTag(models.Model):
    _name = 'dev.tag'
    _description = 'Development Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer('Color')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', 'A tag with this name already exists.')


class DevPageTemplate(models.Model):
    _name = 'dev.page.template'
    _description = 'Documentation Page Template'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    body = fields.Html(sanitize_style=True)
