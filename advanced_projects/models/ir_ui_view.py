from lxml import etree

from odoo import _, fields, models

# The Tasks' Gantt chart is its own view type: Odoo Community has none, and a
# distinct name keeps it clear of Enterprise's "gantt" should that be installed.
GANTT_VIEW = 'project_gantt'
GANTT_ATTRIBUTES = {
    '__validate__',  # ir.ui.view implementation detail
    'class', 'js_class', 'string', 'create', 'edit', 'delete',
    'date_start', 'date_stop', 'group_by', 'link_field', 'link_types', 'milestone_field', 'state_field',
    'assignee_field', 'default_scale',
}


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[(GANTT_VIEW, 'Gantt')])

    def _validate_tag_project_gantt(self, node, name_manager, node_info):
        if not node_info['validate']:
            return
        for child in node.iterchildren(tag=etree.Element):
            if child.tag != 'field':
                self._raise_view_error(_('A Gantt view can only contain fields, got %s', child.tag), child)
        remaining = set(node.attrib) - GANTT_ATTRIBUTES
        if remaining:
            self._raise_view_error(_(
                'Invalid attributes (%(invalid)s) in the Gantt view. Attributes must be in (%(valid)s)',
                invalid=', '.join(sorted(remaining)), valid=', '.join(sorted(GANTT_ATTRIBUTES)),
            ), node)
        for attribute in ('date_start', 'date_stop', 'group_by', 'link_field', 'milestone_field',
                          'state_field', 'assignee_field'):
            field_name = node.get(attribute)
            if field_name and field_name not in name_manager.model._fields:
                self._raise_view_error(_('Field "%(field)s" does not exist in model "%(model)s"',
                                         field=field_name, model=name_manager.model._name), node)
        for attribute in ('date_start', 'date_stop'):
            if not node.get(attribute):
                self._raise_view_error(_('A Gantt view needs a "%s" attribute.', attribute), node)

    def _get_view_info(self):
        return {GANTT_VIEW: {'icon': 'fa fa-align-left'}} | super()._get_view_info()


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(selection_add=[(GANTT_VIEW, 'Gantt')], ondelete={GANTT_VIEW: 'cascade'})
