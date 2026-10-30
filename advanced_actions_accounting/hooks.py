"""Moving the follow-up actions and payment warnings between activities and Actions."""
from odoo import fields

# (activity type, model, action field)
SOURCES = (
    ('advanced_accounting.mail_activity_type_followup', 'res.partner', 'followup_partner_id'),
    ('advanced_accounting.mail_activity_type_recurring_payment_failed', 'recurring.payment', 'recurring_payment_id'),
)


def post_init_hook(env):
    """ The open activities become actions """
    Action = env['advanced.action'].sudo().with_context(advanced_action_no_notify=True)
    for xmlid, model, field_name in SOURCES:
        activity_type = env.ref(xmlid, raise_if_not_found=False)
        if not activity_type:
            continue
        activities = env['mail.activity'].sudo().search([
            ('res_model', '=', model), ('activity_type_id', '=', activity_type.id),
        ])
        for activity in activities:
            Action.create({
                'name': activity.summary or activity_type.name,
                'description': activity.note,
                'user_ids': [(6, 0, activity.user_id.ids)],
                'date_deadline': fields.Datetime.to_datetime(activity.date_deadline),
                'source_app': 'accounting',
                field_name: activity.res_id,
            })
        activities.unlink()


def uninstall_hook(env):
    """ The open actions become activities again """
    Activity = env['mail.activity'].sudo()
    for xmlid, model, field_name in SOURCES:
        activity_type = env.ref(xmlid, raise_if_not_found=False)
        actions = env['advanced.action'].sudo().search([
            (field_name, '!=', False), ('state', 'in', ('open', 'in_progress')),
        ])
        if activity_type:
            model_id = env['ir.model']._get_id(model)
            for action in actions:
                Activity.create({
                    'res_model_id': model_id,
                    'res_id': action[field_name].id,
                    'activity_type_id': activity_type.id,
                    'summary': action.name,
                    'note': action.description,
                    'date_deadline': (action.date_deadline or fields.Datetime.now()).date(),
                    'user_id': (action.user_ids[:1] or action.create_uid).id,
                })
        env['advanced.action'].sudo().search([(field_name, '!=', False)]).unlink()
