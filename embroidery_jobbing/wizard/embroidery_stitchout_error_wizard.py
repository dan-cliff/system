# -*- coding: utf-8 -*-
from odoo import fields, models


class EmbroideryStitchoutErrorWizard(models.TransientModel):
    """Lets the operator record a problem on a stitch out."""
    _name = 'embroidery.stitchout.error.wizard'
    _description = 'Report a Stitch Out Problem'

    stitchout_id = fields.Many2one('embroidery.stitchout', required=True)
    message = fields.Char(string='Problem', required=True, help='e.g. "Upper thread broke on needle 3".')
    code = fields.Char(string='Error Code', help='The code the machine shows, if any.')
    stop = fields.Boolean(string='Machine Stopped', default=True,
                          help='Untick to only log the problem while the machine keeps stitching.')

    def action_report(self):
        self.ensure_one()
        stitchout = self.stitchout_id
        if self.stop:
            if stitchout.state == 'error':
                stitchout._report_error(self.message, self.code or False)
            else:
                stitchout._set_state('error', self.message, self.code or False)
        else:
            stitchout._report_error(self.message, self.code or False)
        return {'type': 'ir.actions.act_window_close'}
