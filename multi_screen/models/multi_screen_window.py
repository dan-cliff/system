from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .multi_screen_placement import _check_rect


class MultiScreenWindow(models.Model):
    """One window of a workspace: which screen, where on it, and what it shows.

    The first window (lowest sequence) is the one the workspace is opened
    from - the installed app's own window - the others are opened for it.
    """

    _name = 'multi.screen.window'
    _description = 'Multi-Screen Workspace Window'
    _order = 'sequence, id'

    layout_id = fields.Many2one('multi.screen.layout', string='Workspace', required=True,
                                ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, default=lambda self: self.env._('Window'))
    screen_number = fields.Integer(
        string='Screen', default=1, required=True,
        help='1 is the left-most screen, 2 the next one to the right, and so on.',
    )
    placement_id = fields.Many2one(
        'multi.screen.placement', string='Placement',
        help='Where on the screen the window goes. Leave empty to use the exact '
             'position below (filled in when windows are saved from the top bar).',
    )
    left_pct = fields.Float(string='Left (%)', default=0.0, digits=(5, 1))
    top_pct = fields.Float(string='Top (%)', default=0.0, digits=(5, 1))
    width_pct = fields.Float(string='Width (%)', default=100.0, digits=(5, 1))
    height_pct = fields.Float(string='Height (%)', default=100.0, digits=(5, 1))
    action_id = fields.Many2one(
        'ir.actions.act_window', string='Opens',
        help='The menu action shown in this window. Takes priority over the page address.',
    )
    url = fields.Char(
        string='Page address',
        help='An Odoo page on this database, e.g. /odoo/sales or /odoo/action-123. '
             'Used when no action is set; empty opens the home screen.',
    )
    open_records_on_id = fields.Many2one(
        'multi.screen.window', string='Open records on',
        domain="[('layout_id', '=', layout_id), ('id', '!=', id)]",
        help='Records clicked in a list or kanban in this window open in that window '
             'instead, so this one keeps its list.',
    )

    @api.constrains('screen_number')
    def _check_screen_number(self):
        for window in self:
            if window.screen_number < 1:
                raise ValidationError(self.env._('The screen number starts at 1.'))

    @api.constrains('left_pct', 'top_pct', 'width_pct', 'height_pct')
    def _check_geometry(self):
        for window in self:
            _check_rect(window)

    @api.constrains('url')
    def _check_url(self):
        for window in self:
            # Only pages of this database: a relative path, not another site.
            if window.url and (not window.url.startswith('/') or window.url.startswith('//')):
                raise ValidationError(self.env._('The page address must start with "/", e.g. /odoo/sales.'))

    @api.constrains('open_records_on_id', 'layout_id')
    def _check_open_records_on(self):
        for window in self:
            target = window.open_records_on_id
            if target and (target == window or target.layout_id != window.layout_id):
                raise ValidationError(self.env._('Records can only be opened on another window of the same workspace.'))

    @api.onchange('placement_id')
    def _onchange_placement_id(self):
        if self.placement_id:
            for field in ('left_pct', 'top_pct', 'width_pct', 'height_pct'):
                self[field] = self.placement_id[field]

    def _target_url(self):
        self.ensure_one()
        if self.action_id:
            return '/odoo/%s' % (self.action_id.path or 'action-%d' % self.action_id.id)
        return self.url or '/odoo'

    def _window_data(self):
        self.ensure_one()
        rect = self.placement_id or self
        return {
            'id': self.id,
            'name': self.name,
            'screen_number': self.screen_number,
            'left_pct': rect.left_pct,
            'top_pct': rect.top_pct,
            'width_pct': rect.width_pct,
            'height_pct': rect.height_pct,
            'url': self._target_url(),
            'action_id': self.action_id.id,
            'open_records_on_id': self.open_records_on_id.id,
        }

    @api.model
    def _values_from_client(self, index, window):
        """Create values for a window reported by the web client, clamped to sane values."""
        def pct(key, default):
            return min(max(float(window.get(key, default) or 0.0), 0.0), 100.0)

        left, top = pct('left_pct', 0.0), pct('top_pct', 0.0)
        url = window.get('url') or ''
        return {
            'sequence': (index + 1) * 10,
            'name': (window.get('name') or self.env._('Window %s', index + 1))[:100],
            'screen_number': max(int(window.get('screen_number') or 1), 1),
            'left_pct': left,
            'top_pct': top,
            'width_pct': max(min(pct('width_pct', 100.0), 100.0 - left), 1.0),
            'height_pct': max(min(pct('height_pct', 100.0), 100.0 - top), 1.0),
            'url': url if url.startswith('/') and not url.startswith('//') else False,
        }
