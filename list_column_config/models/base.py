import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = 'base'

    # List views follow the column layout saved for them in List Column
    # Settings. The result is cached with the view (the 'templates' cache),
    # which is cleared whenever a layout changes.
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if (view_type == 'list' and not self.env.context.get('list_column_config_original')
                and 'list.column.config' in self.env):
            config = self.env['list.column.config']._get_for_view(self._name, view.id)
            if config:
                try:
                    config._apply_to_arch(arch, self)
                except Exception:
                    # a broken layout must never stop the list from opening
                    _logger.exception('Could not apply list column layout %s', config.id)
        return arch, view
