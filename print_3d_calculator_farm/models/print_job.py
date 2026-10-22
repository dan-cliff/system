from markupsafe import Markup, escape

from odoo import _, api, fields, models


class Print3dEstimate(models.Model):
    _inherit = 'print3d.estimate'

    source = fields.Selection(
        selection_add=[('job', 'Print Job')],
        ondelete={'job': 'set default'},
    )


class Print3dMaterial(models.Model):
    _inherit = 'print3d.material'

    pending_consumption_qty = fields.Float(
        string='Filament Not Yet Consumed',
        digits=(16, 6),
        readonly=True,
        help='Filament used by completed print jobs that is still too small to post as a '
             'stock move (in the filament product\'s unit). It is added to the next job.',
    )


class PrintJob(models.Model):
    _inherit = 'print.job'

    print3d_estimate_id = fields.Many2one(
        'print3d.estimate',
        string='3D Print Estimate',
        copy=False,
        help='Filaments, weights and print time read from the job\'s file.',
    )
    print3d_filament_count = fields.Integer(related='print3d_estimate_id.filament_count', string='Filaments Required')
    print3d_total_filament_g = fields.Float(related='print3d_estimate_id.total_filament_g', string='Filament in File (g)')
    print3d_print_time = fields.Char(related='print3d_estimate_id.print_time_display', string='Print Time in File')
    print3d_line_ids = fields.One2many(related='print3d_estimate_id.line_ids', string='Filaments in File')
    print3d_consumed = fields.Boolean(
        string='Filament Consumed',
        copy=False,
        readonly=True,
        help='The filament used by this job has been taken out of stock.',
    )
    print3d_move_ids = fields.Many2many(
        'stock.move',
        'print_job_print3d_stock_move_rel',
        'job_id',
        'move_id',
        string='Filament Stock Moves',
        copy=False,
        readonly=True,
    )
    print3d_move_count = fields.Integer(compute='_compute_print3d_move_count')

    @api.depends('print3d_move_ids')
    def _compute_print3d_move_count(self):
        for job in self:
            job.print3d_move_count = len(job.print3d_move_ids)

    # ─────────────────────────────────────────────────────────────────────
    # Reading the job file
    # ─────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        jobs = super().create(vals_list)
        jobs.filtered('job_file')._print3d_sync_estimate()
        return jobs

    def write(self, vals):
        res = super().write(vals)
        if 'job_file' in vals or 'job_filename' in vals:
            self._print3d_sync_estimate()
        return res

    def _print3d_sync_estimate(self):
        """Read the job's file into its own 3D print estimate."""
        for job in self:
            estimate = job.print3d_estimate_id
            own = estimate and estimate.source == 'job' and not estimate.locked
            if not job.job_file:
                if own:
                    job.print3d_estimate_id = False
                    estimate.unlink()
                continue
            values = {
                'file': job.with_context(bin_size=False).job_file,
                'filename': job.job_filename or job.name,
            }
            if own:
                estimate.write(values)
            else:
                # A linked estimate from an order keeps its own file: the job gets a new one.
                job.print3d_estimate_id = self.env['print3d.estimate'].create({
                    **values,
                    'source': 'job',
                    'partner_id': job.sale_order_id.partner_id.id,
                    'company_id': (job.sale_order_id.company_id or self.env.company).id,
                })
            estimate = job.print3d_estimate_id
            if estimate.state == 'done' and estimate.print_time_seconds and not job.estimated_time_minutes:
                job.estimated_time_minutes = round(estimate.print_time_seconds / 60)

    # ─────────────────────────────────────────────────────────────────────
    # Consuming filament
    # ─────────────────────────────────────────────────────────────────────

    def action_mark_done(self):
        res = super().action_mark_done()
        if self.env['ir.config_parameter'].sudo().get_param('print_3d_calculator_farm.consume_on_done'):
            self.filtered(lambda j: j.state == 'done' and not j.print3d_consumed)._print3d_consume_filament()
        return res

    def _print3d_consume_filament(self):
        """Take the filament each job used out of stock.

        Uses the job's 3D print estimate (weight per filament plus the pricing
        profile's waste allowance) and each material's filament product.
        """
        for job in self:
            estimate = job.print3d_estimate_id
            if not estimate or estimate.state != 'done':
                job.message_post(body=_(
                    'No filament was taken out of stock: the job has no readable print file.'
                ))
                continue
            company = estimate.company_id
            warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                job.message_post(body=_(
                    'No filament was taken out of stock: %s has no warehouse.', company.display_name
                ))
                continue
            waste = 1 + (estimate.profile_id.waste_percent or 0.0) / 100.0
            moves = self.env['stock.move']
            notes = []
            for line in estimate.line_ids.filtered('weight_g'):
                label = line.material_id.name or line.slicer_material or _('Filament %s', line.slot)
                material = line.material_id
                product = material.filament_product_id
                if not product:
                    notes.append(_('%s: no filament product on the material', label))
                    continue
                if product.tracking != 'none':
                    notes.append(_('%s: %s is tracked by lot/serial, so consume it manually',
                                   label, product.display_name))
                    continue
                used = line.weight_g * waste / 1000.0 * material._kg_quantity_in(product.uom_id)
                total = material.pending_consumption_qty + used
                posted = product.uom_id.round(total, rounding_method='DOWN')
                material.sudo().pending_consumption_qty = total - posted
                if posted <= 0:
                    notes.append(_('%(label)s: %(qty)s %(uom)s carried over to the next job',
                                   label=label, qty=round(total, 6), uom=product.uom_id.name))
                    continue
                move = job._print3d_create_move(product, posted, warehouse.lot_stock_id, company)
                moves |= move
                notes.append(_('%(label)s: %(qty)s %(uom)s of %(product)s',
                               label=label, qty=posted, uom=product.uom_id.name,
                               product=product.display_name))
            job.write({'print3d_consumed': True, 'print3d_move_ids': [fields.Command.link(m.id) for m in moves]})
            body = Markup('%s<ul>%s</ul>') % (
                _('Filament taken out of stock:') if moves else _('No filament was taken out of stock:'),
                Markup('').join(Markup('<li>%s</li>') % escape(note) for note in notes)
                or Markup('<li>%s</li>') % _('the file has no filament'),
            )
            job.message_post(body=body)

    def _print3d_create_move(self, product, quantity, location, company):
        self.ensure_one()
        destination = product.with_company(company).property_stock_production
        move = self.env['stock.move'].sudo().create({
            'origin': self.name,
            'company_id': company.id,
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': quantity,
            'location_id': location.id,
            'location_dest_id': destination.id,
            'picked': True,
            'move_line_ids': [fields.Command.create({
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': quantity,
                'location_id': location.id,
                'location_dest_id': destination.id,
            })],
        })
        move._action_done()
        return move

    def action_view_print3d_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Filament Stock Moves'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.print3d_move_ids.ids)],
        }
