def migrate(cr, version):
    # Older versions set the home screen action as every user's Home Action,
    # which made /odoo redirect to /odoo/action-<id>. The home screen is now
    # what /odoo shows by default, so clear those Home Actions.
    cr.execute(
        """
        UPDATE res_users
           SET action_id = NULL
         WHERE action_id = (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'web_home_menu'
                   AND name = 'action_home_screen'
               )
        """
    )
