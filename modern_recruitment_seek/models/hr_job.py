# -*- coding: utf-8 -*-
import uuid

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .hr_contract_type import SEEK_WORK_TYPES

# SEEK's pay codes, so fixed technical selections.
SEEK_PAY_BASES = [
    ('Salaried', 'Salary'),
    ('Hourly', 'Hourly rate'),
    ('SalariedPlusCommission', 'Salary plus commission'),
    ('CommissionOnly', 'Commission only'),
]
SEEK_PAY_INTERVALS = [('Year', 'Per year'), ('Month', 'Per month'), ('Hour', 'Per hour')]
# Technical: where the ad is on SEEK.
SEEK_STATES = [('draft', 'Not posted'), ('posted', 'Posted'), ('closed', 'Closed')]

PROFILE_FIELDS = 'profileId { value }'

AD_PRODUCTS_QUERY = """
query TalentSeekAdProducts($positionProfile: AdvertisementProducts_PositionProfileInput!) {
  advertisementProducts(positionProfile: $positionProfile) {
    products { id { value } label description price { summary } }
  }
}
"""

POST_MUTATION = """
mutation TalentSeekPost($input: PostPositionInput!) {
  postPosition(input: $input) {
    ... on PostPositionPayload_Success {
      positionOpening { documentId { value } }
      positionProfile { %s }
    }
    ... on PostPositionPayload_Conflict {
      conflictingPositionOpening { documentId { value } }
      conflictingPositionProfile { %s }
    }
  }
}
""" % (PROFILE_FIELDS, PROFILE_FIELDS)

UPDATE_MUTATION = """
mutation TalentSeekUpdate($input: UpdatePostedPositionProfileInput!) {
  updatePostedPositionProfile(input: $input) {
    positionProfile { %s }
  }
}
""" % PROFILE_FIELDS

CLOSE_MUTATION = """
mutation TalentSeekClose($input: ClosePostedPositionProfileInput!) {
  closePostedPositionProfile(input: $input) {
    positionProfile { %s }
  }
}
""" % PROFILE_FIELDS


class HrJob(models.Model):
    _inherit = 'hr.job'

    seek_category_id = fields.Many2one(
        'talent.seek.category', string='SEEK Category', domain="[('parent_id', '!=', False)]",
        help='The SEEK sub-category the ad is listed under.',
    )
    seek_location_id = fields.Many2one('talent.seek.location', string='SEEK Location')
    seek_work_type = fields.Selection(
        SEEK_WORK_TYPES, string='SEEK Work Type', compute='_compute_seek_work_type', store=True, readonly=False,
    )
    seek_summary = fields.Char(
        string='Search Summary', size=150,
        help='The short summary SEEK shows in search results (up to 150 characters).',
    )
    seek_pay_basis = fields.Selection(SEEK_PAY_BASES, string='Pay Type', default='Salaried')
    seek_pay_interval = fields.Selection(SEEK_PAY_INTERVALS, string='Pay Interval', default='Year')
    seek_pay_min = fields.Monetary(string='Pay From', currency_field='seek_currency_id')
    seek_pay_max = fields.Monetary(string='Pay To', currency_field='seek_currency_id')
    seek_currency_id = fields.Many2one(
        'res.currency', string='Pay Currency', default=lambda self: self.env.company.currency_id,
    )
    seek_pay_description = fields.Char(
        string='Pay Description', help='How the pay is shown on the ad, e.g. "$80k – $95k + super".',
    )
    seek_ad_product_ids = fields.One2many('talent.seek.ad.product', 'job_id', string='SEEK Ad Products')
    seek_ad_product_id = fields.Many2one(
        'talent.seek.ad.product', string='Ad Product', domain="[('job_id', '=', id)]",
    )
    seek_state = fields.Selection(SEEK_STATES, string='SEEK Ad', default='draft', required=True,
                                  copy=False, tracking=True)
    seek_profile_id = fields.Char(string='SEEK Ad ID', copy=False, readonly=True, index=True)
    seek_opening_id = fields.Char(string='SEEK Position Opening ID', copy=False, readonly=True)
    seek_posted_date = fields.Datetime(string='Posted to SEEK', copy=False, readonly=True)
    seek_application_count = fields.Integer(compute='_compute_seek_application_count')

    @api.depends('contract_type_id')
    def _compute_seek_work_type(self):
        for job in self:
            if job.contract_type_id.seek_work_type:
                job.seek_work_type = job.contract_type_id.seek_work_type

    def _compute_seek_application_count(self):
        source = self.env.ref('modern_recruitment_seek.utm_source_seek', raise_if_not_found=False)
        counts = dict(self.env['hr.applicant'].with_context(active_test=False)._read_group(
            [('job_id', 'in', self.ids), ('source_id', '=', source.id if source else 0)],
            ['job_id'], ['__count'])) if self.ids else {}
        for job in self:
            job.seek_application_count = counts.get(job, 0)

    # ── SEEK payloads ─────────────────────────────────────────────────────

    def _seek_check_ready(self, need_product=True):
        self.ensure_one()
        missing = [label for label, value in (
            (self.env._('SEEK Category'), self.seek_category_id),
            (self.env._('SEEK Location'), self.seek_location_id),
            (self.env._('SEEK Work Type'), self.seek_work_type),
            (self.env._('Pay From'), self.seek_pay_min),
            (self.env._('Pay Currency'), self.seek_currency_id),
            (self.env._('Ad Product'), self.seek_ad_product_id if need_product else True),
        ) if not value]
        if need_product and not self._talent_description_text():
            missing.append(self.env._('Job Summary (the ad text)'))
        if missing:
            raise UserError(self.env._('Fill in these on the SEEK tab first: %s', ', '.join(missing)))
        if self.seek_pay_max and self.seek_pay_max < self.seek_pay_min:
            raise UserError(self.env._('Pay To must be at least Pay From.'))

    def _seek_remuneration(self):
        amount = lambda value: {'currency': self.seek_currency_id.name, 'value': value}
        pay_range = {'intervalCode': self.seek_pay_interval or 'Year', 'minimumAmount': amount(self.seek_pay_min)}
        if self.seek_pay_max:
            pay_range['maximumAmount'] = amount(self.seek_pay_max)
        return {
            'basisCode': self.seek_pay_basis or 'Salaried',
            'ranges': [pay_range],
            'descriptions': [self.seek_pay_description] if self.seek_pay_description else [],
        }

    def _seek_product_profile(self, company):
        """The ad, as SEEK's ad product query takes it."""
        profile = {
            'jobCategories': [self.seek_category_id.seek_id],
            'positionLocation': [self.seek_location_id.seek_id],
            'positionOrganizations': [company.seek_hirer_id],
            'positionTitle': self.name,
            'offeredRemunerationPackage': self._seek_remuneration(),
            'seekAnzWorkTypeCode': self.seek_work_type,
        }
        if self.seek_profile_id:
            profile['profileId'] = self.seek_profile_id
        return profile

    def _seek_position_profile(self, company):
        """The ad, as SEEK's post and update mutations take it."""
        descriptions = [{'descriptionId': 'AdvertisementDetails', 'content': self._talent_description_html()}]
        if self.seek_summary:
            descriptions.append({'descriptionId': 'SearchSummary', 'content': self.seek_summary})
        return {
            'positionTitle': self.name,
            'positionOrganizations': company.seek_hirer_id,
            'jobCategories': self.seek_category_id.seek_id,
            'positionLocation': [self.seek_location_id.seek_id],
            'positionScheduleTypeCodes': ['PartTime' if self.seek_work_type == 'PartTime' else 'FullTime'],
            'seekAnzWorkTypeCode': self.seek_work_type,
            'offeredRemunerationPackage': self._seek_remuneration(),
            'positionFormattedDescriptions': descriptions,
            'seekPartnerMetadata': {'partnerPositionId': str(self.id)},
            'postingInstructions': [{
                'idempotencyId': str(uuid.uuid4()),
                'seekAdvertisementProductId': self.seek_ad_product_id.seek_id,
            }],
        }

    def _seek_contact(self):
        user = self.user_id or self.env.user
        if not user.email:
            raise UserError(self.env._('The Recruiter (%s) needs an email address: SEEK shows it as the ad contact.',
                                       user.name))
        return {
            'name': {'formattedName': user.name},
            'roleCode': 'Recruiter',
            'communication': {'email': [{'address': user.email}]},
        }

    # ── Actions ───────────────────────────────────────────────────────────

    def action_seek_fetch_products(self):
        self.ensure_one()
        self._seek_check_ready(need_product=False)
        api = self.env['talent.seek.api']
        company = api._seek_company(self.company_id)
        data = api._seek_query(AD_PRODUCTS_QUERY, {'positionProfile': self._seek_product_profile(company)}, company)
        products = (data.get('advertisementProducts') or {}).get('products') or []
        if not products:
            raise UserError(self.env._('SEEK offered no ad products for this ad.'))
        selected = self.seek_ad_product_id.seek_id
        self.seek_ad_product_ids = [Command.clear()] + [Command.create({
            'sequence': index,
            'seek_id': product['id']['value'],
            'name': product.get('label') or product['id']['value'],
            'price': (product.get('price') or {}).get('summary') or False,
            'description': product.get('description') or False,
        }) for index, product in enumerate(products)]
        self.seek_ad_product_id = self.seek_ad_product_ids.filtered(lambda p: p.seek_id == selected)[:1] \
            or self.seek_ad_product_ids[:1]

    def action_seek_post(self):
        """Post the ad to SEEK, or update it when it is already posted."""
        self.ensure_one()
        self._seek_check_ready()
        api = self.env['talent.seek.api']
        company = api._seek_company(self.company_id)
        profile = self._seek_position_profile(company)
        if self.seek_profile_id and self.seek_state == 'posted':
            profile['profileId'] = self.seek_profile_id
            api._seek_query(UPDATE_MUTATION, {'input': {'positionProfile': profile}}, company)
            self.message_post(body=self.env._('SEEK ad updated.'))
            return self._seek_notify(self.env._('The SEEK ad was updated.'))
        data = api._seek_query(POST_MUTATION, {'input': {
            'positionOpening': {'postingRequester': {
                'id': company.seek_hirer_id, 'roleCode': 'Company', 'personContacts': [self._seek_contact()],
            }},
            'positionProfile': profile,
        }}, company).get('postPosition') or {}
        opening = data.get('positionOpening') or data.get('conflictingPositionOpening') or {}
        posted = data.get('positionProfile') or data.get('conflictingPositionProfile') or {}
        if not posted:
            raise UserError(self.env._('SEEK did not confirm the ad.'))
        self.write({
            'seek_profile_id': posted['profileId']['value'],
            'seek_opening_id': (opening.get('documentId') or {}).get('value') or False,
            'seek_state': 'posted',
            'seek_posted_date': fields.Datetime.now(),
        })
        self.message_post(body=self.env._('Posted to SEEK (ad %s).', self.seek_profile_id))
        return self._seek_notify(self.env._('The ad was posted to SEEK.'))

    def action_seek_close(self):
        self.ensure_one()
        if not self.seek_profile_id:
            raise UserError(self.env._('This job position has no SEEK ad.'))
        api = self.env['talent.seek.api']
        company = api._seek_company(self.company_id)
        api._seek_query(CLOSE_MUTATION, {'input': {'positionProfile': {'profileId': self.seek_profile_id}}}, company)
        self.seek_state = 'closed'
        self.message_post(body=self.env._('SEEK ad closed.'))
        return self._seek_notify(self.env._('The SEEK ad was closed.'))

    def action_seek_find_location(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Find a SEEK Location'),
            'res_model': 'talent.seek.location.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_id': self.id,
                        'default_query': self._talent_location()['city'] or False},
        }

    def action_seek_applications(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hr_recruitment.crm_case_categ0_act_job')
        source = self.env.ref('modern_recruitment_seek.utm_source_seek')
        action.update({
            'name': self.env._('SEEK Applications'),
            'domain': [('job_id', '=', self.id), ('source_id', '=', source.id)],
            'context': {'default_job_id': self.id, 'active_test': False},
        })
        return action

    def _seek_notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': 'success', 'next': {'type': 'ir.actions.act_window_close'}},
        }
