# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models


def _build_qr_b64(code):
    """Generate a QR code as a base64-encoded SVG string.

    SVG is used instead of PNG because wkhtmltopdf (QtWebKit) ignores explicit
    CSS height on raster images inside table cells and stretches them to fill
    the cell — making every PNG QR non-square.  SVG carries a ``viewBox`` that
    declares an intrinsic 1:1 aspect ratio; the WebKit spec *requires* the
    renderer to honour that ratio when only a CSS width is supplied, so the
    image is always rendered as a perfect square.

    Returns the base64-encoded SVG bytes (no data-URI prefix).
    """
    import qrcode as _qrcode

    qr = _qrcode.QRCode(
        version=None,
        error_correction=_qrcode.constants.ERROR_CORRECT_H,
        border=2,
    )
    qr.add_data(code or '')
    qr.make(fit=True)

    matrix = qr.modules           # list[list[bool]] — pattern only, no quiet zone
    border = qr.border            # quiet-zone modules (= 2)
    n = len(matrix) + 2 * border  # total modules including quiet zone
    cell = 10                     # SVG user units per module

    size = n * cell               # canvas is always square: size × size
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {size} {size}"'
        f' width="{size}" height="{size}"'
        f' shape-rendering="crispEdges">',
        f'<rect width="{size}" height="{size}" fill="white"/>',
    ]
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                x = (c + border) * cell
                y = (r + border) * cell
                parts.append(
                    f'<rect x="{x}" y="{y}"'
                    f' width="{cell}" height="{cell}" fill="black"/>'
                )
    parts.append('</svg>')

    svg_bytes = ''.join(parts).encode('ascii')
    return base64.b64encode(svg_bytes).decode('ascii')


class Membership(models.Model):
    _name = 'membership.membership'
    _description = 'Membership'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Member Number',
        readonly=True,
        copy=False,
        index=True,
        default='New',
    )
    active = fields.Boolean(string='Active', default=True)

    # ── Contact ───────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        tracking=True,
    )
    partner_name = fields.Char(
        string='Member Name',
        related='partner_id.name',
        store=True,
    )

    # ── Address (readonly mirrors of partner) ─────────────────────────────
    street = fields.Char(related='partner_id.street', readonly=True)
    street2 = fields.Char(related='partner_id.street2', readonly=True)
    city = fields.Char(related='partner_id.city', readonly=True)
    state_id = fields.Many2one(
        'res.country.state',
        related='partner_id.state_id',
        readonly=True,
    )
    zip = fields.Char(related='partner_id.zip', readonly=True)
    country_id = fields.Many2one(
        'res.country',
        related='partner_id.country_id',
        readonly=True,
    )
    phone = fields.Char(related='partner_id.phone', readonly=True)
    email = fields.Char(related='partner_id.email', readonly=True)

    # ── Membership details ────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Membership Product',
        domain="[('is_membership', '=', True)]",
        tracking=True,
    )
    status_id = fields.Many2one(
        'membership.status',
        string='Status',
        tracking=True,
    )
    status_color = fields.Integer(
        string='Status Color',
        related='status_id.color',
        store=False,
    )
    status_fold = fields.Boolean(
        string='Status Fold',
        related='status_id.fold',
        store=False,
    )
    date_issued = fields.Date(string='Issued Date', tracking=True)
    date_expiry = fields.Date(string='Expiry Date', tracking=True)
    notes = fields.Text(string='Notes')

    # ── QR Code ───────────────────────────────────────────────────────────
    qr_image = fields.Binary(
        string='QR Code Image',
        readonly=True,
        copy=False,
        attachment=False,
        help='Pre-generated square RGB PNG of the member QR code.',
    )

    # ── Create ────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('membership.sequence') or 'New'
            if not vals.get('qr_image') and vals.get('name') and vals['name'] != 'New':
                try:
                    vals['qr_image'] = _build_qr_b64(vals['name'])
                except Exception:
                    pass
        records = super().create(vals_list)
        # Generate QR for any that were created with a valid name but no QR yet
        for rec in records:
            if not rec.qr_image and rec.name and rec.name != 'New':
                try:
                    rec.qr_image = _build_qr_b64(rec.name)
                except Exception:
                    pass
        return records

    # ── QR helpers ────────────────────────────────────────────────────────

    def get_qr_code_src(self):
        """Return a data:image/svg+xml;base64 URI for use in QWeb PDF templates."""
        self.ensure_one()
        img_b64 = self.qr_image
        if img_b64:
            if isinstance(img_b64, bytes):
                img_b64 = img_b64.decode('ascii')
            return f'data:image/svg+xml;base64,{img_b64}'
        try:
            img_b64 = _build_qr_b64(self.name)
            return f'data:image/svg+xml;base64,{img_b64}'
        except Exception:
            return ''

    def get_svg_inline(self):
        """Return the QR code as an inline SVG Markup object (102pt × 102pt).

        Inline SVG bypasses wkhtmltopdf's img rendering pipeline which stretches
        images inside table cells, guaranteeing a perfect square on the card.
        """
        from markupsafe import Markup
        import base64 as _b64
        self.ensure_one()
        img_b64 = self.qr_image
        if not img_b64:
            try:
                img_b64 = _build_qr_b64(self.name)
            except Exception:
                return Markup('')
        if isinstance(img_b64, bytes):
            img_b64 = img_b64.decode('ascii')
        try:
            svg_xml = _b64.b64decode(img_b64).decode('ascii')
            svg_xml = svg_xml.replace('<svg ', '<svg style="display:block;width:102pt;height:102pt;" ', 1)
            return Markup(svg_xml)
        except Exception:
            return Markup('')

    @api.model
    def _populate_qr_images(self):
        """Regenerate qr_image as SVG for every membership.

        Called on module update so that records created with the old PNG
        generator are upgraded to the square-guaranteed SVG format.
        """
        for membership in self.search([]):
            try:
                membership.qr_image = _build_qr_b64(membership.name)
            except Exception:
                pass

    # ── Action buttons ────────────────────────────────────────────────────

    def action_send_email(self):
        """Open the email wizard for this membership."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Email',
            'res_model': 'membership.email.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_membership_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
        }

    def action_print_membership_card(self):
        """Print the membership card report."""
        self.ensure_one()
        return self.env.ref(
            'membership_management.action_report_membership_card'
        ).report_action(self)

    def action_open_letter_wizard(self):
        """Open the letter generation wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Letter',
            'res_model': 'membership.letter.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_membership_id': self.id,
            },
        }
