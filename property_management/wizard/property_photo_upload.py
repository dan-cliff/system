# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class PropertyPhotoUpload(models.TransientModel):
    """Upload several photos to a property's photo library at once."""
    _name = 'property.photo.upload'
    _description = 'Upload Property Photos'

    property_id = fields.Many2one('property.property', required=True, ondelete='cascade')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'property_photo_upload_attachment_rel', 'wizard_id', 'attachment_id',
        string='Photos')
    date_taken = fields.Date(string='Taken On', default=fields.Date.context_today)

    def action_upload(self):
        self.ensure_one()
        images = self.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith('image/'))
        if not images:
            raise UserError(self.env._('Choose one or more image files to upload.'))
        sequence = max(self.property_id.photo_ids.mapped('sequence') or [0])
        vals_list = []
        for attachment in images:
            sequence += 1
            caption = (attachment.name or '').rsplit('.', 1)[0]
            vals_list.append({
                'property_id': self.property_id.id,
                'name': caption,
                'image_1920': attachment.datas,
                'date_taken': self.date_taken,
                'sequence': sequence,
            })
        self.env['property.photo'].create(vals_list)
        # The uploads were only a carrier for the images: drop them.
        self.attachment_ids.sudo().unlink()
        return {'type': 'ir.actions.act_window_close'}
