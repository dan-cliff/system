from odoo import api, fields, models
from odoo.exceptions import ValidationError

# A fixed Yes / No / N/A answer: the form shows each question's "Comments / Further
# Information" field only when it is answered Yes or No, so the values are technical.
CHECKLIST_ANSWERS = [('yes', 'Yes'), ('no', 'No'), ('na', 'N/A')]

# (field name, question) - each question also has a "<field name>_comment" field.
EQUIPMENT_QUESTIONS = [
    ('equip_first_aid', 'First aid kit suitable for activity available?'),
    ('equip_sun_safety', 'Safe sun equipment (hats, sunscreen, water, etc)?'),
    ('equip_drinking_water', 'Drinking water?'),
    ('equip_clothing_ppe', 'Suitable personal clothing and protective equipment?'),
    ('equip_communications', 'Communications equipment?'),
    ('equip_shelter', 'Accommodation and shelter?'),
    ('equip_navigation', 'Navigation equipment?'),
    ('equip_standards', 'Equipment complies with relevant standards and in good condition?'),
    ('equip_site_access', 'Site access, permissions and fees organised?'),
]
GOVERNING_QUESTIONS = [
    ('gov_guidelines_exist', 'Do guidelines from a governing body exist for this activity?'),
    ('gov_guidelines_followed', 'Have they been referred to and followed?'),
]


class RiskActivityMixin(models.AbstractModel):
    """Activity Details, Minimum Equipment / Facilities and Governing Bodies /
    Associations / Legislation questions shared by Risk Assessments and Risk Templates."""
    _name = 'risk.activity.mixin'
    _description = 'Risk Activity Details Mixin'

    # Activity Details
    activity_location = fields.Text(string='Activity Location')
    activity_leader_id = fields.Many2one('res.users', string='Activity Leader Name')
    safety_officer_id = fields.Many2one('res.users', string="Safety Officer's Name")
    activity_start = fields.Datetime(string='Starting At', required=True)
    activity_end = fields.Datetime(string='Finishing At')

    # Minimum Equipment / Facilities
    equip_first_aid = fields.Selection(CHECKLIST_ANSWERS, string='First aid kit suitable for activity available?')
    equip_first_aid_comment = fields.Text(string='First aid kit suitable for activity available? Comments')
    equip_sun_safety = fields.Selection(CHECKLIST_ANSWERS, string='Safe sun equipment (hats, sunscreen, water, etc)?')
    equip_sun_safety_comment = fields.Text(string='Safe sun equipment (hats, sunscreen, water, etc)? Comments')
    equip_drinking_water = fields.Selection(CHECKLIST_ANSWERS, string='Drinking water?')
    equip_drinking_water_comment = fields.Text(string='Drinking water? Comments')
    equip_clothing_ppe = fields.Selection(CHECKLIST_ANSWERS, string='Suitable personal clothing and protective equipment?')
    equip_clothing_ppe_comment = fields.Text(string='Suitable personal clothing and protective equipment? Comments')
    equip_communications = fields.Selection(CHECKLIST_ANSWERS, string='Communications equipment?')
    equip_communications_comment = fields.Text(string='Communications equipment? Comments')
    equip_shelter = fields.Selection(CHECKLIST_ANSWERS, string='Accommodation and shelter?')
    equip_shelter_comment = fields.Text(string='Accommodation and shelter? Comments')
    equip_navigation = fields.Selection(CHECKLIST_ANSWERS, string='Navigation equipment?')
    equip_navigation_comment = fields.Text(string='Navigation equipment? Comments')
    equip_standards = fields.Selection(CHECKLIST_ANSWERS, string='Equipment complies with relevant standards and in good condition?')
    equip_standards_comment = fields.Text(string='Equipment complies with relevant standards and in good condition? Comments')
    equip_site_access = fields.Selection(CHECKLIST_ANSWERS, string='Site access, permissions and fees organised?')
    equip_site_access_comment = fields.Text(string='Site access, permissions and fees organised? Comments')

    # Governing Bodies / Associations / Legislation
    gov_guidelines_exist = fields.Selection(CHECKLIST_ANSWERS, string='Do guidelines from a governing body exist for this activity?')
    gov_guidelines_exist_comment = fields.Text(string='Do guidelines from a governing body exist for this activity? Comments')
    gov_guidelines_followed = fields.Selection(CHECKLIST_ANSWERS, string='Have they been referred to and followed?')
    gov_guidelines_followed_comment = fields.Text(string='Have they been referred to and followed? Comments')

    @api.constrains('activity_start', 'activity_end')
    def _check_activity_dates(self):
        for record in self:
            if record.activity_end and record.activity_start and record.activity_end < record.activity_start:
                raise ValidationError('Finishing At cannot be before Starting At.')

    def _checklist_rows(self, section):
        """Return [(question, answer label, comment), ...] for 'equipment' or 'governing'."""
        self.ensure_one()
        questions = EQUIPMENT_QUESTIONS if section == 'equipment' else GOVERNING_QUESTIONS
        answers = dict(CHECKLIST_ANSWERS)
        return [
            (question, answers.get(self[name], ''), self[name + '_comment'] or '')
            for name, question in questions
        ]
