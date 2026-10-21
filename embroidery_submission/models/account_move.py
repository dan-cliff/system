# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    embroidery_submission_ids = fields.Many2many(
        'embroidery.submission', string='Embroidery Costings', compute='_compute_embroidery_submission_ids',
    )
    embroidery_submission_count = fields.Integer(compute='_compute_embroidery_submission_ids')
    embroidery_line_ids = fields.Many2many(
        'account.move.line', string='Embroidery Lines', compute='_compute_embroidery_submission_ids',
    )
    embroidery_cost_total = fields.Monetary(
        string='Embroidery Cost', compute='_compute_embroidery_submission_ids',
        help='Total recorded cost (stitches, colour changes, machine time and fees) of the embroidery on this invoice.',
    )

    @api.depends('invoice_line_ids.embroidery_submission_id', 'invoice_line_ids.quantity')
    def _compute_embroidery_submission_ids(self):
        for move in self:
            lines = move.invoice_line_ids.filtered('embroidery_submission_id')
            move.embroidery_line_ids = lines
            move.embroidery_submission_ids = lines.embroidery_submission_id
            move.embroidery_submission_count = len(lines.embroidery_submission_id)
            move.embroidery_cost_total = sum(
                line.embroidery_submission_id.currency_id._convert(
                    line.embroidery_submission_id.cost_total * line.quantity,
                    move.currency_id,
                    move.company_id,
                    move.invoice_date or fields.Date.context_today(move),
                )
                for line in lines
            )

    def action_view_embroidery_submissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Embroidery Costings'),
            'res_model': 'embroidery.submission',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.embroidery_submission_ids.ids)],
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    embroidery_submission_id = fields.Many2one(
        'embroidery.submission', string='Embroidery Submission', index='btree_not_null', copy=True, readonly=True,
    )
    embroidery_stitch_count = fields.Integer(related='embroidery_submission_id.stitch_count', string='Stitches')
    embroidery_color_change_count = fields.Integer(related='embroidery_submission_id.color_change_count',
                                                   string='Colour Changes')
    embroidery_duration = fields.Char(related='embroidery_submission_id.duration_display', string='Est. Duration')
    embroidery_stitch_cost = fields.Monetary(related='embroidery_submission_id.stitch_cost', string='Stitch Cost',
                                             currency_field='embroidery_currency_id')
    embroidery_color_change_cost = fields.Monetary(related='embroidery_submission_id.color_change_cost',
                                                   string='Colour Change Fees',
                                                   currency_field='embroidery_currency_id')
    embroidery_machine_cost = fields.Monetary(related='embroidery_submission_id.machine_cost',
                                              string='Machine Time Cost', currency_field='embroidery_currency_id')
    embroidery_setup_cost = fields.Monetary(related='embroidery_submission_id.setup_cost', string='Setup Fee',
                                            currency_field='embroidery_currency_id')
    embroidery_cost_total = fields.Monetary(related='embroidery_submission_id.cost_total', string='Cost per Piece',
                                            currency_field='embroidery_currency_id')
    embroidery_currency_id = fields.Many2one(related='embroidery_submission_id.currency_id',
                                             string='Embroidery Currency')
