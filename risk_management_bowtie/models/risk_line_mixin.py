import base64

from odoo import fields, models

from .risk_bowtie_svg import render_bowtie_svg


class RiskLineMixin(models.AbstractModel):
    _inherit = 'risk.line.mixin'

    # Bowtie analysis. The Unwanted Event above is the bowtie's Top Event; each
    # concrete model adds its own bowtie_threat_ids / bowtie_consequence_ids.
    bowtie_hazard = fields.Text(
        string='Hazard',
        help='Something in or around the activity with the potential to cause harm, which is '
             'normally present and needed for the activity, e.g. "Working at height".',
    )
    has_bowtie = fields.Boolean(compute='_compute_has_bowtie')

    def _compute_has_bowtie(self):
        for line in self:
            line.has_bowtie = bool(
                line.bowtie_hazard or line.bowtie_threat_ids or line.bowtie_consequence_ids
            )

    def get_bowtie_svg(self):
        """The bowtie diagram as SVG markup - shown by the Bowtie Diagram dialog and the PDF."""
        self.ensure_one()
        return render_bowtie_svg(self)

    def _bowtie_report_image(self, max_aspect=0.47, full_width=1700):
        """Data URI and width (%) of the bowtie as an image for the PDF appendix.

        An <img> keeps the diagram's proportions under wkhtmltopdf. A diagram
        ``full_width`` px wide fills the page and smaller ones keep the same
        scale; tall diagrams are narrowed so the whole bowtie fits on one
        landscape page.
        """
        self.ensure_one()
        svg = str(self.get_bowtie_svg())
        viewbox = svg.split('viewBox="', 1)[1].split('"', 1)[0].split()
        width, height = float(viewbox[2]), float(viewbox[3])
        aspect = height / width if width else 1
        width_pct = min(100, 100 * width / full_width, 100 * max_aspect / aspect if aspect else 100)
        return {
            'src': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode(),
            'width': round(width_pct, 1),
        }

    def action_open_bowtie(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'risk_bowtie_diagram',
            'name': 'Bowtie: %s' % (self.name or ''),
            'target': 'new',
            'params': {'res_model': self._name, 'res_id': self.id},
            'context': {'dialog_size': 'extra-large'},
        }

    def _bowtie_copy_vals(self):
        """Values recreating this risk's bowtie on another risk line."""
        self.ensure_one()
        return {
            'bowtie_hazard': self.bowtie_hazard,
            'bowtie_threat_ids': [(0, 0, threat._bowtie_copy_vals()) for threat in self.bowtie_threat_ids],
            'bowtie_consequence_ids': [
                (0, 0, consequence._bowtie_copy_vals()) for consequence in self.bowtie_consequence_ids
            ],
        }
