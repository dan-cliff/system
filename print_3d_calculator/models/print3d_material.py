import re

from odoo import api, fields, models


class Print3dMaterial(models.Model):
    _name = 'print3d.material'
    _description = '3D Print Material'
    _order = 'sequence, name'

    name = fields.Char(string='Material', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    slicer_names = fields.Char(
        string='Slicer Names',
        help='Names the slicers use for this material, separated by commas '
             '(e.g. "PLA, PLA+, PLA Basic"). Filaments read from a print file '
             'are matched to the material by these names.',
    )
    density = fields.Float(
        string='Density (g/cm³)',
        digits=(16, 3),
        default=1.24,
        help='Used to turn filament length or model volume into weight.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    cost_per_kg = fields.Monetary(
        string='Cost per kg',
        help='Filament cost per kilogram. Filled in from the filament product '
             'when one is set.',
    )
    filament_product_id = fields.Many2one(
        'product.product',
        string='Filament Product',
        help='Inventory product for this filament. Its cost is used as the cost per kg.',
    )
    spool_weight_kg = fields.Float(
        string='Spool Weight (kg)',
        default=1.0,
        digits=(16, 3),
        help='Filament weight of one unit of the filament product, when it is '
             'sold per spool rather than by weight.',
    )
    colour = fields.Char(string='Colour', help='Display colour, e.g. #FF5733')
    description = fields.Text(string='Description', translate=True,
                              help='Shown to customers on the website quote.')
    website_published = fields.Boolean(
        string='Offer on Website',
        default=True,
        help='Customers can choose this material on the website quote.',
    )

    @api.onchange('filament_product_id', 'spool_weight_kg')
    def _onchange_filament_product_id(self):
        for material in self:
            if material.filament_product_id:
                material.cost_per_kg = material._get_cost_per_kg()

    def _get_cost_per_kg(self):
        """Current cost per kg, from the filament product when there is one."""
        self.ensure_one()
        product = self.filament_product_id
        if not product:
            return self.cost_per_kg
        price = product.standard_price
        if product.currency_id and product.currency_id != self.currency_id:
            price = product.currency_id._convert(
                price, self.currency_id, self.env.company, fields.Date.context_today(self)
            )
        kg = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        if kg and product.uom_id._has_common_reference(kg):
            return product.uom_id._compute_price(price, kg)
        return price / (self.spool_weight_kg or 1.0)

    def _match_names(self):
        self.ensure_one()
        names = {self.name.strip().lower()}
        names.update(n.strip().lower() for n in (self.slicer_names or '').split(',') if n.strip())
        return names

    @api.model
    def _find_for_slicer_name(self, slicer_name, materials=None):
        """Best material for a filament type read from a print file."""
        materials = materials if materials is not None else self.search([])
        name = (slicer_name or '').strip().lower()
        if not name:
            return self.browse()
        for material in materials:
            if name in material._match_names():
                return material
        # "PLA Basic", "PLA-CF" → try the leading word ("pla") as a fallback
        base = re.split(r'[\s\-_+/]', name)[0]
        for material in materials:
            if base in material._match_names():
                return material
        return self.browse()
