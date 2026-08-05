from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Purchase integration ──────────────────────────────────────────────────
    print_farm_restock_to_purchase = fields.Boolean(
        string='Link Restock Orders to Purchase Orders',
        config_parameter='print_farm_jobs.restock_to_purchase',
        help='When enabled, confirming a Restock Order automatically creates a '
             'draft Purchase Order in the Purchase module for all ordered lines.',
    )

    # ── Sales integration ─────────────────────────────────────────────────────
    print_farm_sale_to_print_job = fields.Boolean(
        string='Create Print Jobs from Sale Orders',
        config_parameter='print_farm_jobs.sale_to_print_job',
        help='When enabled, confirming a Sale Order automatically creates a '
             'Print Job for each order line whose product has a Default Filament set.',
    )
