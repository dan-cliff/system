from lxml import etree

from odoo import api, models


class Base(models.AbstractModel):
    _inherit = 'base'

    def _nextcloud_rule(self):
        if 'nextcloud.folder.rule' not in self.env or self._transient or self._abstract:
            return None
        return self.env['nextcloud.folder.rule']._rules_by_model().get(self._name)

    # Records of a model with "Create Automatically" get their folder queued
    # as soon as they are created; the cron creates it in the background.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        rule_info = records and records._nextcloud_rule()
        if rule_info and rule_info[1]:
            rule = self.env['nextcloud.folder.rule'].sudo().browse(rule_info[0])
            domain = rule._get_domain()
            matching = records.sudo().filtered_domain(domain) if domain else records
            self.env['nextcloud.folder']._queue(rule, matching)
        return records

    # Forms of a model with a folder rule get a "Folder" button.
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and self._nextcloud_rule():
            self._nextcloud_add_button(arch)
        return arch, view

    @api.model
    def _nextcloud_add_button(self, arch):
        if arch.xpath("//button[@name='action_nextcloud_folder']"):
            return
        button = etree.Element('button', {
            'name': 'action_nextcloud_folder',
            'type': 'object',
            'class': 'oe_stat_button',
            'icon': 'fa-folder-open',
            'invisible': 'not id',
            'title': self.env._("Open this record's Nextcloud folder"),
        })
        info = etree.SubElement(button, 'div', {'class': 'o_stat_info'})
        etree.SubElement(info, 'span', {'class': 'o_stat_value'}).text = self.env._("Folder")
        etree.SubElement(info, 'span', {'class': 'o_stat_text'}).text = 'Nextcloud'
        box = next(iter(arch.xpath("//div[@name='button_box']")), None)
        if box is None:
            container = next(iter(arch.xpath('./sheet')), arch)
            box = etree.Element('div', {'name': 'button_box', 'class': 'oe_button_box'})
            container.insert(0, box)
        box.insert(0, button)

    def action_nextcloud_folder(self):
        """Open the record's Nextcloud folder, creating it first if needed."""
        self.ensure_one()
        self.check_access('read')
        folder = self.env['nextcloud.folder']._get_or_create_for(self)
        if folder.state != 'done':
            folder._create_in_nextcloud(raise_error=True)
        return {'type': 'ir.actions.act_url', 'url': folder.url, 'target': 'new'}
