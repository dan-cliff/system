# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests.common import TransactionCase


class ManufacturingCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [Command.link(cls.env.ref('mrp.group_mrp_routings').id)]
        cls.company = cls.env.company
        cls.company.write({
            'mrp_terminal_identify_badge': True,
            'mrp_terminal_identify_name': True,
            'mrp_terminal_require_pin': True,
            'mrp_terminal_offline': True,
            'mrp_terminal_close_production': True,
        })
        cls.workcenter = cls.env['mrp.workcenter'].create({'name': 'Assembly Bench', 'company_id': cls.company.id})
        cls.other_workcenter = cls.env['mrp.workcenter'].create({'name': 'Paint Booth', 'company_id': cls.company.id})
        cls.component = cls.env['product.product'].create({'name': 'Timber', 'is_storable': True})
        cls.product = cls.env['product.product'].create({'name': 'Stool', 'is_storable': True})
        cls.lot_product = cls.env['product.product'].create({
            'name': 'Candle Batch', 'is_storable': True, 'tracking': 'lot'})
        cls.bom = cls._bom(cls.product)
        cls.lot_bom = cls._bom(cls.lot_product)
        cls.alice = cls.env['hr.employee'].create({
            'name': 'Alice Maker', 'barcode': 'TMFG-0042', 'pin': '1234', 'company_id': cls.company.id})
        cls.bob = cls.env['hr.employee'].create({
            'name': 'Bob Builder', 'barcode': '88017781', 'pin': '9999', 'company_id': cls.company.id})

    @classmethod
    def _bom(cls, product, workcenters=None):
        workcenters = workcenters or [cls.workcenter]
        return cls.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_qty': 1,
            'bom_line_ids': [Command.create({'product_id': cls.component.id, 'product_qty': 2})],
            'operation_ids': [Command.create({
                'name': 'Op %s' % wc.name, 'workcenter_id': wc.id, 'time_cycle_manual': 30, 'sequence': i,
            }) for i, wc in enumerate(workcenters)],
        })

    def _production(self, product=None, qty=3, bom=None):
        product = product or self.product
        production = self.env['mrp.production'].create({
            'product_id': product.id,
            'product_qty': qty,
            'bom_id': (bom or (self.lot_bom if product == self.lot_product else self.bom)).id,
        })
        production.action_confirm()
        self.env['stock.quant']._update_available_quantity(
            self.component, production.location_src_id, 100)
        production.action_assign()
        return production

    def _event(self, action, workorder, employee=None, when=None, **extra):
        self._seq = getattr(self, '_seq', 0) + 1
        event = dict(id='evt-%s-%s' % (self._testMethodName, self._seq), action=action,
                     workorder_id=workorder.id, **extra)
        workcenter = workorder.workcenter_id.sudo()
        from odoo import fields
        return workcenter._terminal_apply(event, (employee or self.alice).sudo(), when or fields.Datetime.now(),
                                          offline=bool(when))
