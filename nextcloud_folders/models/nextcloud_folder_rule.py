import re

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

# {field} or {field.subfield} in a folder path
PLACEHOLDER = re.compile(r'\{([\w.]+)\}')
# characters Nextcloud, Windows and SMB shares can't hold in a folder name
UNSAFE_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
SPECIAL_PLACEHOLDERS = ('model', 'id')
MAX_SEGMENT_LENGTH = 200


def clean_segment(value):
    """``value`` made safe as a single folder name."""
    value = UNSAFE_CHARACTERS.sub('-', value or '')
    value = re.sub(r'\s+', ' ', value).strip().rstrip('.').strip()
    return value[:MAX_SEGMENT_LENGTH].strip() or '_'


class NextcloudFolderRule(models.Model):
    _name = 'nextcloud.folder.rule'
    _description = 'Nextcloud Folder Rule'
    _order = 'sequence, id'
    _rec_name = 'model_id'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        domain=[('transient', '=', False), ('abstract', '=', False)],
        help="Records of this model get a Nextcloud folder and a Folder button on their form.")
    model = fields.Char(string='Model Name', related='model_id.model', store=True, index=True)
    folder_path = fields.Char(
        string='Folder Path', required=True, default='{model}/{display_name}',
        help="Where each record's folder is created, under the root folder set in Settings. "
             "Each / starts a subfolder. Use {field} for a field of the record (e.g. {name}, "
             "{partner_id}, {date}) or {field.subfield} (e.g. {partner_id.city}); {model} is the "
             "model's name and {id} the record's id. Characters a folder name can't hold "
             "(/ \\ : * ? \" < > |) are replaced by -.")
    auto_create = fields.Boolean(
        string='Create Automatically',
        help="Create the folder in the background as soon as a record is saved. Otherwise it is "
             "created the first time someone presses the record's Folder button.")
    filter_domain = fields.Char(
        string='Only For', default='[]',
        help="Records that get a folder automatically. Leave empty for all records. "
             "Any record can still get one with its Folder button.")
    public_link = fields.Boolean(
        string='Create Public Link',
        help="Also create a read-only public share link for each folder (anyone with the link "
             "can view and download its files). The Folder button keeps opening the signed-in "
             "link; the public link shows on the folder record.")
    folder_count = fields.Integer(string='Folders', compute='_compute_folder_count')
    example_path = fields.Char(string='Example', compute='_compute_example_path')

    _model_uniq = models.Constraint('UNIQUE (model_id)', 'This model already has a folder rule.')

    def _compute_folder_count(self):
        counts = dict(self.env['nextcloud.folder']._read_group(
            [('rule_id', 'in', self.ids)], ['rule_id'], ['__count']))
        for rule in self:
            rule.folder_count = counts.get(rule, 0)

    @api.depends('model_id', 'folder_path')
    def _compute_example_path(self):
        Api = self.env['nextcloud.api']
        for rule in self:
            example = False
            if rule.model_id and rule.folder_path:
                try:
                    # the latest record, as an example of the path
                    record = self.env[rule.model_id.model].search([], limit=1, order='id desc')
                    if record:
                        example = '/'.join(Api._root_folder() + rule._folder_segments(record))
                except Exception:  # noqa: BLE001 - only a preview
                    example = False
            rule.example_path = example

    @api.constrains('model_id', 'folder_path')
    def _check_folder_path(self):
        for rule in self:
            if not [part for part in rule.folder_path.split('/') if part.strip()]:
                raise ValidationError(_("Enter a folder path."))
            Model = self.env[rule.model_id.model]
            for placeholder in PLACEHOLDER.findall(rule.folder_path):
                if placeholder in SPECIAL_PLACEHOLDERS:
                    continue
                current = Model
                names = placeholder.split('.')
                for index, name in enumerate(names):
                    field = current._fields.get(name)
                    if not field:
                        raise ValidationError(_(
                            "The folder path uses {%(placeholder)s}, but %(model)s has no field "
                            "\"%(field)s\".", placeholder=placeholder,
                            model=current._description, field=name))
                    if field.relational:
                        current = self.env[field.comodel_name]
                    elif index < len(names) - 1:
                        raise ValidationError(_(
                            "The folder path uses {%(placeholder)s}, but \"%(field)s\" isn't a "
                            "link to another record, so it can't be followed by a dot.",
                            placeholder=placeholder, field=name))

    # ------------------------------------------------------------------
    # Cache: the models with a rule (looked up on every form and create)
    # ------------------------------------------------------------------

    @api.model
    @tools.ormcache()
    def _rules_by_model(self):
        """{model name: (rule id, create automatically)} of the active rules."""
        rules = self.sudo().search([])
        return {rule.model: (rule.id, rule.auto_create) for rule in rules}

    @api.model
    def _rule_for(self, model_name):
        rule_id = self._rules_by_model().get(model_name, (False,))[0]
        return self.sudo().browse(rule_id)

    @api.model
    def _clear_caches(self):
        # Rules decide which forms get the Folder button.
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        self._clear_caches()
        return rules

    def write(self, vals):
        res = super().write(vals)
        self._clear_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._clear_caches()
        return res

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _placeholder_value(self, record, placeholder):
        if placeholder == 'model':
            return self.model_id.name
        if placeholder == 'id':
            return str(record.id)
        *path, name = placeholder.split('.')
        value = record
        for step in path:
            value = value[:1][step]
            if not value:
                return ''
        return self._format_value(value._fields[name], value[:1][name])

    def _format_value(self, field, value):
        if field.type in ('many2one', 'many2many', 'one2many', 'reference', 'many2one_reference'):
            if field.type == 'many2one_reference':
                return str(value or '')
            return ', '.join(value.mapped('display_name')) if value else ''
        if field.type == 'date':
            return value.strftime('%d/%m/%Y') if value else ''
        if field.type == 'datetime':
            return fields.Datetime.context_timestamp(self, value).strftime('%d/%m/%Y') if value else ''
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, '') if value else ''
        if field.type == 'boolean':
            return field.string if value else ''
        if value is False or value is None:
            return ''
        return str(value)

    def _folder_segments(self, record):
        """The record's folder path below the root folder, as folder names."""
        self.ensure_one()
        segments = []
        for part in self.folder_path.split('/'):
            if not part.strip():
                continue
            text = PLACEHOLDER.sub(lambda m: self._placeholder_value(record, m.group(1)), part)
            segments.append(clean_segment(text))
        return segments

    def _get_domain(self):
        self.ensure_one()
        return safe_eval(self.filter_domain or '[]', {'uid': self.env.uid, 'user': self.env.user})

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_create_existing(self):
        """Queue a folder for every record (matching Only For) without one."""
        self.ensure_one()
        Folder = self.env['nextcloud.folder'].sudo()
        existing = set(Folder.search([('res_model', '=', self.model)]).mapped('res_id'))
        records = self.env[self.model].sudo().search(self._get_domain())
        missing = records.filtered(lambda r: r.id not in existing)
        Folder._queue(self, missing)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("%s folders queued; they are created in the background.", len(missing)),
            },
        }

    def action_open_folders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Folders"),
            'res_model': 'nextcloud.folder',
            'view_mode': 'list,form',
            'domain': [('rule_id', '=', self.id)],
            'context': {'default_rule_id': self.id},
        }
