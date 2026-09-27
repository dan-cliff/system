from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    receipt_attachment_id = fields.Many2one(
        "ir.attachment",
        string="SMS Receipt Image",
        readonly=True,
        copy=False,
    )
    receipt_download_url = fields.Char(
        string="Receipt Download URL",
        compute="_compute_receipt_download_url",
    )

    @api.depends("receipt_attachment_id", "receipt_attachment_id.access_token")
    def _compute_receipt_download_url(self):
        for order in self:
            attachment = order.receipt_attachment_id
            if attachment and attachment.access_token:
                order.receipt_download_url = "%s/pos/receipt/%s/%s" % (
                    order.get_base_url(),
                    attachment.id,
                    attachment.access_token,
                )
            else:
                order.receipt_download_url = False

    def _create_sms_receipt_attachment(self, ticket_image):
        """Store the JPEG the POS front end just rendered for this SMS as an
        ir.attachment, so receipt_download_url has something to point at
        before the SMS template below is rendered.
        """
        self.ensure_one()
        if not ticket_image:
            return
        image_data = ticket_image.split(",", 1)[-1] if "," in ticket_image else ticket_image
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "Receipt-%s.jpg" % (self.pos_reference or self.name),
            "type": "binary",
            "datas": image_data,
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "image/jpeg",
        })
        attachment.generate_access_token()
        self.receipt_attachment_id = attachment

    def action_sent_message_on_sms(self, phone, full_ticket_image, basic_ticket_image=False):
        if self and self.config_id.module_pos_sms and self.config_id.sms_receipt_template_id and phone:
            self.ensure_one()
            self._create_sms_receipt_attachment(full_ticket_image or basic_ticket_image)
        return super().action_sent_message_on_sms(phone, full_ticket_image, basic_ticket_image)
