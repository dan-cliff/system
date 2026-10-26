"""Contracts moved out of the CRM: remove what they left behind as noupdate
data (their number sequence and the external IDs of their emails), and
reword the stage guidance that mentioned them, unless an administrator has
already changed it (stages are noupdate)."""
from odoo import SUPERUSER_ID, api

GUIDANCE = {
    'modern_crm.stage_negotiation': (
        '<p>Agree the terms, then create the contract and send it for signature.</p>',
        '<p>Agree the terms and get the go-ahead, then confirm the sale.</p>'),
    'modern_crm.stage_won': (
        '<p>Signed and sold: confirm the sale and invoice it.</p>',
        '<p>Sold: confirm the sale and invoice it.</p>'),
}

CONTRACT_DATA = ('seq_modern_crm_contract', 'mail_template_contract_signature_request',
                 'mail_template_contract_signed')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    data = env['ir.model.data'].search([('module', '=', 'modern_crm'), ('name', 'in', CONTRACT_DATA)])
    for record in data:
        if record.model in env:
            env[record.model].browse(record.res_id).exists().unlink()
    data.unlink()
    for xmlid, (old, new) in GUIDANCE.items():
        stage = env.ref(xmlid, raise_if_not_found=False)
        if stage and stage.guidance == old:
            stage.guidance = new
