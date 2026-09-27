from odoo import http
from odoo.http import content_disposition, request
from odoo.tools import consteq


class PosSmsReceiptController(http.Controller):

    @http.route(
        "/pos/receipt/<int:attachment_id>/<string:access_token>",
        type="http",
        auth="public",
        csrf=False,
    )
    def download_receipt(self, attachment_id, access_token):
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if not attachment or not attachment.access_token or not consteq(attachment.access_token, access_token):
            return request.not_found()
        return request.make_response(
            attachment.raw,
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", content_disposition(attachment.name)),
            ],
        )
