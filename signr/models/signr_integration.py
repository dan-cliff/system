# -*- coding: utf-8 -*-
"""Sign requests raised straight from other apps' records.

Each integration below is switched on in Settings › Sign'r. When it is on,
the forms of its model get two smart buttons: "Request Signature" (pick a
template and send it, filled in from the record) and "Sign Requests" (the
requests raised from the record so far). The buttons are added to the form
when it is loaded, so Sign'r needs no add-on per app; the view cache is
cleared whenever the switches change.
"""
from lxml import etree

from odoo import api, models
from odoo.exceptions import UserError

# key, model, modules (any one installed), title, description
INTEGRATIONS = [
    ('applicant', 'hr.applicant', ('modern_recruitment', 'hr_recruitment'), 'Talent Applications',
     'Send offer letters, employment contracts and other documents to applicants for signature, '
     'from their application in Talent.'),
    ('crm_opportunity', 'modern.crm.opportunity', ('modern_crm',), 'CRM Opportunities',
     'Send proposals, order forms and agreements for signature from an opportunity in CRM.'),
    ('crm_contract', 'modern.crm.contract', ('modern_crm',), 'CRM Sales',
     'Send documents for signature from the contracts under CRM › Sales, e.g. variations, '
     'change requests and renewals.'),
    ('sale_order', 'sale.order', ('sale',), 'Sales',
     'Send order forms, quotes and terms of trade for signature from a quotation or sales order.'),
    ('employee_contract', 'hr.version', ('hr',), 'Employee Contracts',
     "Send employment contracts and contract variations for signature from an employee's contract, "
     'filled in with its job, dates and pay.'),
    ('employee', 'hr.employee', ('hr',), 'Employees',
     'Send policies, acknowledgements, change requests and other documents for signature from an '
     'employee record.'),
    ('incident', 'incident.report', ('incident_management',), 'Incidents',
     'Send witness statements, incident reports and sign-offs for signature from an incident.'),
    ('injury', 'injury.rtw.case', ('injury_management',), 'Injury Management',
     'Send return to work plans, consent forms and declarations for signature from a return to '
     'work case.'),
]
PARAM = 'signr.integration_%s'
INTEGRATION_MODELS = {model for _key, model, _modules, _title, _desc in INTEGRATIONS}


def integration_models(env):
    """The models whose forms get the Sign'r smart buttons."""
    params = env['ir.config_parameter'].sudo()
    return {model for key, model, _modules, _title, _desc in INTEGRATIONS
            if params.get_param(PARAM % key) and model in env}


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        # The smart buttons follow the Settings switches, so they are part of
        # the cached form's key.
        key = super()._get_view_cache_key(view_id, view_type, **options)
        if view_type == 'form' and self._name in INTEGRATION_MODELS:
            key += (self._name in integration_models(self.env),)
        return key

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and self._name in integration_models(self.env):
            self._signr_add_buttons(arch)
        return arch, view

    @api.model
    def _signr_add_buttons(self, arch):
        box = next(iter(arch.xpath("//div[@name='button_box']")), None)
        if box is None:
            sheet = next(iter(arch.xpath('//sheet')), None)
            if sheet is None:
                return
            box = etree.Element('div', {'name': 'button_box', 'class': 'oe_button_box'})
            sheet.insert(0, box)
        request = etree.Element('button', {
            'name': 'action_signr_request_signature', 'type': 'object', 'class': 'oe_stat_button',
            'icon': 'fa-pencil-square-o', 'groups': 'signr.group_signr_user',
            'invisible': 'not id', 'help': self.env._('Send a document for signature, filled in from this record'),
        })
        info = etree.SubElement(request, 'div', {'class': 'o_stat_info'})
        etree.SubElement(info, 'span', {'class': 'o_stat_text'}).text = self.env._('Request')
        etree.SubElement(info, 'span', {'class': 'o_stat_text'}).text = self.env._('Signature')
        history = etree.Element('button', {
            'name': 'action_signr_view_requests', 'type': 'object', 'class': 'oe_stat_button',
            'icon': 'fa-file-text-o', 'groups': 'signr.group_signr_user', 'invisible': 'not id',
            'help': self.env._('The sign requests raised from this record'),
        })
        info = etree.SubElement(history, 'div', {'class': 'o_stat_info'})
        etree.SubElement(info, 'span', {'class': 'o_stat_text'}).text = self.env._('Sign')
        etree.SubElement(info, 'span', {'class': 'o_stat_text'}).text = self.env._('Requests')
        box.insert(0, history)
        box.insert(0, request)

    def action_signr_request_signature(self):
        """A new sign request for this record, in a dialog."""
        self.ensure_one()
        templates = self.env['signr.template'].search([('model_name', '=', self._name)])
        if not templates:
            raise UserError(self.env._(
                "There is no Sign'r template for %s yet. Add one under Sign'r › Templates, or ask your "
                "Sign'r administrator to.", self.env['ir.model']._get(self._name).name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Request Signature'),
            'res_model': 'signr.request',
            'view_mode': 'form',
            'views': [(self.env.ref('signr.signr_request_view_form_quick').id, 'form')],
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
                'signr_quick': True,
            },
        }

    def action_signr_view_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('signr.action_signr_request')
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        action['context'] = {'default_res_model': self._name, 'default_res_id': self.id}
        return action
