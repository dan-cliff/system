# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import AccessError

GROUP_PRODUCE = 'advanced_manufacturing.group_production_produce'
GROUP_USER = 'advanced_manufacturing.group_manufacturing_user'


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    # New orders take the user's home Organisation units, not their product's.
    _org_parent_field = False

    def _check_produce_permission(self):
        """Manufacturing Orders: Produce. Users given Manufacturing permissions
        need it to mark orders as done; the Work Centre app (which runs with
        the server's rights) and users of Odoo's own Manufacturing groups only
        are not affected."""
        user = self.env.user
        if self.env.su or not user.has_group(GROUP_USER) or user.has_group(GROUP_PRODUCE):
            return
        raise AccessError(_('You need the "Manufacturing Orders: Produce" permission to mark manufacturing orders as done.'))

    def button_mark_done(self):
        self._check_produce_permission()
        return super().button_mark_done()


class MrpBom(models.Model):
    _inherit = 'mrp.bom'
    _org_parent_field = False


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'
    _org_parent_field = False
