import re

from odoo import _, api, fields, models


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
        compute='_compute_cost_per_kg',
        inverse='_inverse_cost_per_kg',
        help='Filament cost per kilogram. With a filament product it is worked out '
             'from the product\'s purchase price; otherwise enter it here.',
    )
    manual_cost_per_kg = fields.Monetary(
        string='Manual Cost per kg',
        help='Cost per kg used when the material has no filament product.',
    )
    cost_source = fields.Char(
        string='Cost Source',
        compute='_compute_cost_per_kg',
        help='Where the cost per kg comes from.',
    )
    filament_product_id = fields.Many2one(
        'product.product',
        string='Filament Product',
        help='Inventory product for this filament. Its purchase price gives the cost '
             'per kg, and completed print jobs can consume it from stock.',
    )
    spool_weight_kg = fields.Float(
        string='Spool Weight (kg)',
        default=1.0,
        digits=(16, 3),
        help='Filament weight of one unit of the filament product, when it is '
             'bought and stocked per spool rather than by weight.',
    )
    colour = fields.Char(string='Colour', help='Display colour, e.g. #FF5733')
    description = fields.Text(string='Description', translate=True,
                              help='Shown to customers on the website quote.')
    website_published = fields.Boolean(
        string='Offer on Website',
        default=True,
        help='Customers can choose this material on the website quote.',
    )

    @api.depends(
        'manual_cost_per_kg', 'spool_weight_kg', 'currency_id', 'filament_product_id.uom_id',
        'filament_product_id.seller_ids.price', 'filament_product_id.seller_ids.product_uom_id',
        'filament_product_id.seller_ids.currency_id', 'filament_product_id.seller_ids.sequence',
    )
    @api.depends_context('company')
    def _compute_cost_per_kg(self):
        for material in self:
            if not material.filament_product_id:
                material.cost_per_kg = material.manual_cost_per_kg
                material.cost_source = _('Entered manually')
                continue
            material.cost_per_kg, material.cost_source = material._purchase_cost_per_kg()

    def _inverse_cost_per_kg(self):
        for material in self:
            if not material.filament_product_id:
                material.manual_cost_per_kg = material.cost_per_kg

    def _kg_quantity_in(self, uom):
        """How many of `uom` hold one kg of this filament."""
        self.ensure_one()
        kg = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        if kg and uom and uom._has_common_reference(kg):
            return kg._compute_quantity(1.0, uom, round=False)
        # Counted in units (spools): one unit holds spool_weight_kg of filament.
        return 1.0 / (self.spool_weight_kg or 1.0)

    def _purchase_cost_per_kg(self):
        """Cost per kg from the filament product's purchase price.

        Uses the product's main vendor price (Purchase tab) when it has one,
        otherwise the product's Cost (kept up to date by stock valuation).
        """
        self.ensure_one()
        product = self.filament_product_id
        company = self.env.company
        date = fields.Date.context_today(self)
        sellers = product.seller_ids.filtered(
            lambda s: s.price and (not s.product_id or s.product_id == product)
            and (not s.company_id or s.company_id == company)
        ).sorted(lambda s: (s.sequence, s.min_qty, s.id))
        if sellers:
            seller = sellers[0]
            price = seller.currency_id._convert(seller.price, self.currency_id, company, date)
            uom = seller.product_uom_id or product.uom_id
            source = _('Vendor price from %s', seller.partner_id.display_name)
        else:
            price = product.with_company(company).standard_price
            if product.cost_currency_id and product.cost_currency_id != self.currency_id:
                price = product.cost_currency_id._convert(price, self.currency_id, company, date)
            uom = product.uom_id
            source = _('Product cost')
        return price * self._kg_quantity_in(uom), source

    def _get_cost_per_kg(self):
        """Current cost per kg (from the filament product's purchase price when set)."""
        self.ensure_one()
        return self.cost_per_kg

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
