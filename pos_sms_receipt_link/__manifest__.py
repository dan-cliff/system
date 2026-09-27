# Copyright 2026 Bendigo Scouts
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

{
    "name": "POS SMS Receipt Link",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Add a no-login download link for the receipt image to POS SMS receipts",
    "description": """
POS SMS Receipt Link
=====================
The standard `pos_sms` module lets you text a customer a plain text
confirmation, but discards the receipt image the POS front end already
generates for that message and gives you no way to link to it.

This module:

- Saves the receipt image POS already renders when a "Send by SMS" is
  triggered as an `ir.attachment` on the order.
- Exposes a `receipt_download_url` field on `pos.order` pointing at a
  public, no-login route that serves that image, guarded by a random
  access token on the attachment (not the portal).
- Updates the stock "POS: Sent Order Confirmation via Text" SMS template
  to reference `{{object.receipt_download_url}}` instead of
  `{{object.access_url}}` (which only ever resolves to the generic,
  login-gated `/my` portal page for this model).
""",
    "author": "Bendigo Scouts",
    "website": "https://github.com/dan-cliff/bendigoscouts",
    "license": "LGPL-3",
    "depends": ["pos_sms"],
    "data": [
        "data/sms_template_data.xml",
    ],
    "installable": True,
    "application": False,
}
