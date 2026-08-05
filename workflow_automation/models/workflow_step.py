# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import json
import logging
import re
import secrets
import string
import traceback
import time as _time

import requests
from requests.exceptions import RequestException

from odoo import _, api, fields, models
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)

# Regex for {{expression}} template rendering
_TEMPLATE_RE = re.compile(r'\{\{(.+?)\}\}')

# Headers redacted in the API call log for the API Call step type
_API_SENSITIVE_HEADERS = frozenset({
    'authorization', 'x-api-key', 'x-auth-token', 'x-api-secret',
})


# ── Word list for the Random Generator step type ──────────────────────────── #
# ~450 common English words (5-7 chars) suitable for readable random values
# and human-readable password generation.
_WF_WORD_LIST = (
    'abbey', 'abide', 'ablaze', 'abrupt', 'absent', 'absorb', 'accent',
    'accept', 'access', 'accord', 'active', 'actual', 'adjust', 'admire',
    'advent', 'aerial', 'afford', 'afraid', 'agency', 'agenda', 'agile',
    'alarm', 'album', 'alert', 'alien', 'align', 'alley', 'allow',
    'alloy', 'alone', 'alpine', 'alter', 'amber', 'ample', 'anchor',
    'angel', 'angle', 'ankle', 'annex', 'apple', 'apply', 'apron',
    'arena', 'argue', 'arise', 'armor', 'arrow', 'asset', 'atlas',
    'attic', 'audio', 'audit', 'avert', 'avoid', 'awake', 'award',
    'azure', 'badge', 'baked', 'basic', 'batch', 'beach', 'beard',
    'bench', 'birch', 'blade', 'blast', 'blaze', 'blend', 'bliss',
    'bloom', 'blown', 'board', 'bonus', 'boost', 'boxer', 'brace',
    'brave', 'bread', 'break', 'breed', 'bribe', 'brief', 'brisk',
    'broil', 'brook', 'brush', 'build', 'burst', 'cable', 'cache',
    'camel', 'candy', 'cargo', 'carry', 'cedar', 'chain', 'chalk',
    'chaos', 'charm', 'chase', 'chief', 'child', 'civic', 'claim',
    'clash', 'class', 'clean', 'clear', 'cliff', 'climb', 'clock',
    'close', 'cloud', 'clout', 'coach', 'cobra', 'comet', 'comic',
    'coral', 'court', 'cover', 'craft', 'crane', 'crash', 'cream',
    'creek', 'crest', 'crime', 'crisp', 'cross', 'crown', 'crush',
    'cyber', 'cycle', 'daily', 'daisy', 'dance', 'datum', 'debug',
    'delta', 'depth', 'dense', 'depot', 'derby', 'devil', 'digit',
    'draft', 'drama', 'drape', 'dream', 'dress', 'drift', 'drink',
    'drive', 'drone', 'drown', 'dwarf', 'eager', 'eagle', 'early',
    'earth', 'eight', 'elite', 'ember', 'empty', 'enjoy', 'entry',
    'envoy', 'epoch', 'equal', 'event', 'exact', 'extra', 'fable',
    'fairy', 'faith', 'fancy', 'favor', 'feast', 'fence', 'fever',
    'field', 'fifth', 'fight', 'flame', 'flare', 'flash', 'flask',
    'fleet', 'flesh', 'float', 'flood', 'floor', 'flour', 'flute',
    'focus', 'force', 'forge', 'frame', 'frank', 'fresh', 'front',
    'frost', 'fruit', 'funny', 'fused', 'gains', 'gauge', 'gavel',
    'ghost', 'giant', 'given', 'glare', 'glass', 'globe', 'gloss',
    'glove', 'glued', 'grace', 'grade', 'grain', 'grand', 'grant',
    'graph', 'grass', 'grave', 'great', 'green', 'greet', 'grief',
    'grove', 'guard', 'guide', 'guild', 'gusto', 'habit', 'happy',
    'hardy', 'haven', 'heart', 'heavy', 'hedge', 'helix', 'homer',
    'honor', 'horse', 'hotel', 'hover', 'human', 'humid', 'ideal',
    'image', 'inbox', 'index', 'indie', 'inner', 'input', 'intel',
    'intro', 'ivory', 'jewel', 'joker', 'judge', 'juice', 'juicy',
    'kayak', 'kindle', 'knack', 'knife', 'knock', 'known', 'label',
    'laser', 'laugh', 'layer', 'lemon', 'level', 'light', 'linen',
    'links', 'local', 'lodge', 'logic', 'loose', 'lotus', 'lucid',
    'lunch', 'lyric', 'magic', 'major', 'mango', 'maple', 'march',
    'merit', 'mercy', 'metal', 'micro', 'might', 'model', 'money',
    'month', 'moral', 'morph', 'motor', 'mount', 'mouse', 'mouth',
    'movie', 'music', 'naive', 'nerve', 'niche', 'night', 'noble',
    'north', 'notch', 'novel', 'nurse', 'nymph', 'oasis', 'ocean',
    'onion', 'onset', 'opera', 'orbit', 'order', 'organ', 'outer',
    'oxide', 'ozone', 'paint', 'panel', 'panic', 'paper', 'party',
    'pasta', 'patch', 'pause', 'peace', 'pearl', 'penny', 'perch',
    'phase', 'phone', 'photo', 'piano', 'pilot', 'pixel', 'pizza',
    'place', 'plain', 'plane', 'plant', 'plate', 'plaza', 'point',
    'poker', 'polar', 'power', 'press', 'price', 'prime', 'print',
    'prior', 'prize', 'probe', 'proud', 'prove', 'pulse', 'pupil',
    'quake', 'queen', 'quick', 'quiet', 'quota', 'quote', 'radar',
    'radio', 'raise', 'rally', 'ranch', 'range', 'rapid', 'ratio',
    'reach', 'ready', 'rebel', 'realm', 'recap', 'regal', 'relay',
    'remix', 'reset', 'rider', 'ridge', 'rifle', 'right', 'rigid',
    'risky', 'rival', 'river', 'robin', 'robot', 'rocky', 'rough',
    'round', 'route', 'royal', 'rugby', 'ruler', 'rural', 'rusty',
    'saint', 'salad', 'sauce', 'savvy', 'scale', 'scene', 'scent',
    'scope', 'score', 'scout', 'screw', 'serum', 'setup', 'seven',
    'shard', 'share', 'shark', 'sharp', 'shelf', 'shell', 'shift',
    'shiny', 'shore', 'short', 'shout', 'sigma', 'since', 'sixth',
    'skill', 'skull', 'slate', 'slice', 'slide', 'slope', 'small',
    'smart', 'smile', 'smoke', 'snake', 'solar', 'solid', 'solve',
    'sonic', 'south', 'space', 'spark', 'speed', 'spend', 'spice',
    'spike', 'spine', 'spite', 'spray', 'stack', 'stage', 'stake',
    'steel', 'steep', 'steer', 'stone', 'store', 'storm', 'story',
    'strap', 'straw', 'strip', 'study', 'style', 'sugar', 'suite',
    'super', 'surge', 'swamp', 'swift', 'swirl', 'sword', 'syrup',
    'table', 'teach', 'tense', 'tenth', 'terra', 'thick', 'think',
    'third', 'thorn', 'three', 'throw', 'tiger', 'title', 'today',
    'token', 'torch', 'total', 'tough', 'tower', 'toxic', 'track',
    'trade', 'train', 'trail', 'trait', 'trend', 'trial', 'tribe',
    'trick', 'trout', 'truck', 'truly', 'trust', 'truth', 'tulip',
    'twist', 'ultra', 'under', 'union', 'unity', 'upper', 'urban',
    'usual', 'valid', 'value', 'valve', 'vapor', 'vault', 'venue',
    'verse', 'video', 'vigor', 'viral', 'visit', 'vista', 'vital',
    'vivid', 'vocal', 'voice', 'voter', 'water', 'weave', 'wedge',
    'weird', 'wheat', 'white', 'whole', 'wider', 'woman', 'world',
    'worry', 'worth', 'wrath', 'write', 'yacht', 'yield', 'young',
    'youth', 'zebra',
)


def _redact_api_headers(headers_dict):
    """Return a copy of *headers_dict* with sensitive values replaced."""
    return {
        k: ('***REDACTED***' if k.lower() in _API_SENSITIVE_HEADERS else v)
        for k, v in (headers_dict or {}).items()
    }


def _resolve_dot_path(data, path):
    """Navigate *path* (dot-separated) into *data* dict/list and return the leaf.

    Integer segments are treated as list indices::

        _resolve_dot_path([{"id": 5}], "0.id")   → 5
        _resolve_dot_path({"data": [{"id": 5}]}, "data.0.id")  → 5
        _resolve_dot_path({"id": 5}, "id")        → 5
    """
    val = data
    for segment in path.split('.'):
        if val is None:
            return None
        if isinstance(val, list):
            try:
                val = val[int(segment)]
            except (ValueError, IndexError):
                return None
        elif isinstance(val, dict):
            val = val.get(segment)
        else:
            return None
    return val


class WfStep(models.Model):
    """A single step within a workflow automation.

    Steps are executed sequentially (ordered by *sequence*).  Each step can
    optionally check a condition before running and may signal the engine to
    skip the remaining steps ('stop') or continue normally.
    """

    _name = 'wf.step'
    _description = 'Workflow Step'
    _order = 'sequence, id'

    # ------------------------------------------------------------------ #
    # Core identity fields                                                 #
    # ------------------------------------------------------------------ #

    workflow_id = fields.Many2one(
        'wf.automation',
        string='Workflow',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Step Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    step_type = fields.Selection(
        selection=[
            ('create_record', 'Create Record'),
            ('update_record', 'Update Record'),
            ('delete_record', 'Delete Record'),
            ('add_activity', 'Add Activity'),
            ('post_message', 'Post Message'),
            ('send_notification', 'Send Bus Notification'),
            ('send_email', 'Send Email'),
            ('generate_report', 'Generate Report'),
            ('python_code', 'Execute Python Code'),
            ('api_call', 'API Call'),
            ('random_generator', 'Random Generator'),
            ('conditional_branch', 'Conditional Branch'),
            ('stop_workflow', 'Stop Workflow'),
            ('trigger_workflow', 'Trigger Another Workflow'),
        ],
        string='Step Type',
        required=True,
    )

    # ------------------------------------------------------------------ #
    # Generate Report fields                                               #
    # ------------------------------------------------------------------ #

    generate_report_ids = fields.Many2many(
        'report.builder',
        relation='wf_step_generate_report_rel',
        column1='step_id',
        column2='report_id',
        string='Reports to Generate',
        help='Select one or more reports to generate. '
             'Generated files are stored as attachments on the trigger record '
             'and made available to subsequent Send Email steps.',
    )
    generate_report_attach_to_record = fields.Boolean(
        string='Attach to Trigger Record',
        default=True,
        help='When checked, the generated report files are attached to the trigger record.',
    )

    # ------------------------------------------------------------------ #
    # Step condition                                                       #
    # ------------------------------------------------------------------ #

    condition_type = fields.Selection(
        selection=[
            ('none', 'No Condition'),
            ('domain', 'Domain Filter'),
            ('python', 'Python Expression'),
        ],
        string='Condition',
        default='none',
    )
    condition_domain = fields.Char(
        string='Condition Domain',
        default='[]',
        help='Odoo domain evaluated against the trigger record.',
    )
    condition_python = fields.Text(
        string='Condition Python',
        help='Python expression returning True/False.',
    )
    on_condition_fail = fields.Selection(
        selection=[
            ('skip', 'Skip This Step'),
            ('stop_workflow', 'Stop Entire Workflow'),
        ],
        string='On Condition Fail',
        default='skip',
    )

    # ------------------------------------------------------------------ #
    # Canvas layout                                                        #
    # ------------------------------------------------------------------ #

    canvas_x = fields.Float(string='Canvas X', default=100.0)
    canvas_y = fields.Float(string='Canvas Y', default=100.0)

    out_connection_ids = fields.One2many(
        'wf.step.connection', 'from_step_id', string='Outgoing Connections',
        copy=False,
    )
    in_connection_ids = fields.One2many(
        'wf.step.connection', 'to_step_id', string='Incoming Connections',
        copy=False,
    )

    # ------------------------------------------------------------------ #
    # Target record resolution                                             #
    # ------------------------------------------------------------------ #

    target_record_type = fields.Selection(
        selection=[
            ('trigger', 'Trigger Record'),
            ('relation', 'Related Record (field)'),
            ('domain', 'Domain Search'),
        ],
        string='Target Record',
        default='trigger',
    )
    target_relation_field_id = fields.Many2one(
        'ir.model.fields',
        string='Relation Field',
        domain="[('model_id', '=', workflow_id.model_id), ('ttype', 'in', ['many2one', 'many2many', 'one2many'])]",
        help='Field on the trigger record pointing to the target record(s).',
    )
    target_model_id = fields.Many2one(
        'ir.model',
        string='Target Model',
        domain=[('transient', '=', False)],
    )
    target_domain = fields.Char(
        string='Target Domain',
        default='[]',
    )

    # Computed helpers — expose model technical names for the domain widget.
    # The domain widget's options="{'model': '<field_name>'}" reads the *value*
    # of the named field to know which model to build the filter against.
    workflow_model_name = fields.Char(
        string='Workflow Model Name',
        related='workflow_id.model_name',
        readonly=True,
        store=False,
        help='Technical model name of the workflow trigger model (feeds domain widget).',
    )
    target_model_name = fields.Char(
        string='Target Model Name',
        related='target_model_id.model',
        readonly=True,
        store=False,
        help='Technical model name of the chosen target model (feeds domain widget).',
    )

    # ------------------------------------------------------------------ #
    # Create record                                                        #
    # ------------------------------------------------------------------ #

    create_model_id = fields.Many2one(
        'ir.model',
        string='Create In Model',
        domain=[('transient', '=', False)],
    )
    create_link_field_id = fields.Many2one(
        'ir.model.fields',
        string='Link-back Field',
        help='Many2one field on the newly created record that should point back to the trigger record.',
    )

    # ------------------------------------------------------------------ #
    # Field mappings (create + update)                                    #
    # ------------------------------------------------------------------ #

    field_mapping_ids = fields.One2many(
        'wf.step.field.mapping',
        'step_id',
        string='Field Mappings',
    )

    # Computed — drives domain on field_mapping_ids.field_id
    mapping_model_id = fields.Many2one(
        'ir.model',
        string='Mapping Model',
        compute='_compute_mapping_model_id',
        store=False,
    )

    @api.depends(
        'step_type', 'create_model_id', 'workflow_id.model_id',
        'target_record_type', 'target_relation_field_id', 'target_model_id',
    )
    def _compute_mapping_model_id(self):
        for step in self:
            if step.step_type == 'create_record':
                step.mapping_model_id = step.create_model_id
            elif step.step_type == 'update_record':
                if step.target_record_type == 'trigger':
                    step.mapping_model_id = step.workflow_id.model_id
                elif step.target_record_type == 'relation' and step.target_relation_field_id:
                    comodel = step.target_relation_field_id.relation
                    if comodel:
                        step.mapping_model_id = self.env['ir.model']._get(comodel)
                    else:
                        step.mapping_model_id = False
                elif step.target_record_type == 'domain':
                    step.mapping_model_id = step.target_model_id
                else:
                    step.mapping_model_id = False
            else:
                step.mapping_model_id = False

    # ------------------------------------------------------------------ #
    # Activity fields                                                      #
    # ------------------------------------------------------------------ #

    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type')
    activity_summary = fields.Char(string='Summary')
    activity_note = fields.Html(string='Note')
    activity_deadline_days = fields.Integer(string='Deadline (days)', default=1)
    activity_user_type = fields.Selection(
        selection=[
            ('current_user', 'Current User'),
            ('record_user', 'Record Responsible User'),
            ('specific_user', 'Specific User'),
        ],
        string='Assign To',
        default='current_user',
    )
    activity_user_id = fields.Many2one('res.users', string='Specific User')
    activity_user_field_id = fields.Many2one(
        'ir.model.fields',
        string='User Field',
        domain="[('model_id', '=', workflow_id.model_id), ('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
        help='Field on the trigger record holding the user to assign the activity to.',
    )

    # ------------------------------------------------------------------ #
    # Post message fields                                                  #
    # ------------------------------------------------------------------ #

    message_post_method = fields.Selection(
        selection=[
            ('comment', 'Comment (public)'),
            ('note', 'Internal Note'),
        ],
        string='Post As',
        default='comment',
    )
    message_body = fields.Html(string='Message Body')

    # ------------------------------------------------------------------ #
    # Bus notification fields                                              #
    # ------------------------------------------------------------------ #

    notification_level = fields.Selection(
        selection=[
            ('info', 'Info'),
            ('success', 'Success'),
            ('warning', 'Warning'),
            ('danger', 'Danger'),
        ],
        string='Notification Level',
        default='info',
    )
    notification_message = fields.Char(string='Notification Message')
    notification_target = fields.Selection(
        selection=[
            ('current_user', 'Current User'),
            ('specific_users', 'Specific Users'),
        ],
        string='Notify',
        default='current_user',
    )
    notification_user_ids = fields.Many2many(
        'res.users',
        relation='wf_step_notification_user_rel',
        column1='step_id',
        column2='user_id',
        string='Target Users',
    )

    # ------------------------------------------------------------------ #
    # Email fields                                                         #
    # ------------------------------------------------------------------ #

    email_type = fields.Selection(
        selection=[
            ('template', 'Use Email Template'),
            ('inline', 'Compose Inline'),
        ],
        string='Email Type',
        default='template',
    )
    email_template_id = fields.Many2one(
        'mail.template',
        string='Email Template',
    )
    email_subject = fields.Char(string='Subject')
    email_body = fields.Html(string='Email Body')
    email_to_type = fields.Selection(
        selection=[
            ('field', 'Field on Record'),
            ('specific_users', 'Specific Users'),
        ],
        string='Send To',
        default='field',
        help='How the recipient(s) are determined for inline emails.',
    )
    email_to_field_id = fields.Many2one(
        'ir.model.fields',
        string='To (field)',
        domain="[('model_id', '=', workflow_id.model_id)]",
        help='Field on the trigger record that holds the recipient email address.',
    )
    email_to_user_ids = fields.Many2many(
        'res.users',
        relation='wf_step_email_user_rel',
        column1='step_id',
        column2='user_id',
        string='Recipients',
        help='Send the email to these specific users.',
    )
    # Report attachments for Send Email
    email_attach_report_ids = fields.Many2many(
        'report.builder',
        relation='wf_step_email_attach_report_rel',
        column1='step_id',
        column2='report_id',
        string='Attach Reports',
        help='Attach the output of these reports to the outgoing email. '
             'Only reports that appear in a Generate Report step earlier in this '
             'workflow are available.',
    )

    # ------------------------------------------------------------------ #
    # Report name inclusion (Post Message / Send Notification / API Call) #
    # ------------------------------------------------------------------ #

    include_report_names = fields.Boolean(
        string='Include Report Names',
        default=False,
        help='When checked, the names of the reports from any preceding '
             'Generate Report steps will be appended to the message/body.',
    )

    # ------------------------------------------------------------------ #
    # Python code fields                                                   #
    # ------------------------------------------------------------------ #

    python_code = fields.Text(
        string='Python Code',
        help='Python code to execute. Use "result = ..." to capture a return value.',
    )
    python_result_var = fields.Char(
        string='Result Variable',
        help='If set, the value of "result" from the Python code is stored in this variable name.',
    )

    # ------------------------------------------------------------------ #
    # Conditional branch fields                                            #
    # ------------------------------------------------------------------ #

    branch_condition_type = fields.Selection(
        selection=[
            ('domain', 'Domain'),
            ('python', 'Python Expression'),
        ],
        string='Branch Condition',
        default='domain',
    )
    branch_condition_domain = fields.Char(string='Branch Domain', default='[]')
    branch_condition_python = fields.Text(string='Branch Python')
    branch_action = fields.Selection(
        selection=[
            ('stop', 'Block this path (condition not met)'),
            ('continue', 'Follow connections anyway (ignore condition)'),
        ],
        string='Branch Behaviour',
        default='stop',
        help=(
            'Block this path: when the condition is not met, no connections '
            'from this branch are followed.  Other parallel branches are '
            'unaffected.\n\n'
            'Follow connections anyway: connections are evaluated even when '
            'the condition fails — useful when routing logic lives entirely '
            'in the connection filters.\n\n'
            'To abort an entire workflow on failure, connect this branch to '
            'a Stop Workflow step via the appropriate connection condition.'
        ),
    )

    # ------------------------------------------------------------------ #
    # Random Generator fields                                             #
    # ------------------------------------------------------------------ #

    rand_generate_type = fields.Selection(
        selection=[
            ('word',     'Word(s)'),
            ('number',   'Number'),
            ('password', 'Password'),
        ],
        string='Generate',
        default='word',
        help='What type of random value to generate.',
    )

    # ── Word sub-options ─────────────────────────────────────────────── #

    rand_word_count = fields.Integer(
        string='Number of Words',
        default=1,
        help='How many random words to generate.',
    )
    rand_word_spaces = fields.Boolean(
        string='Separate with Spaces',
        default=True,
        help='When checked, words are joined with a space. '
             'Uncheck to concatenate them directly.',
    )

    # ── Number sub-options ───────────────────────────────────────────── #

    rand_number_min = fields.Integer(
        string='Minimum',
        default=1,
        help='Lower bound of the random integer range (inclusive).',
    )
    rand_number_max = fields.Integer(
        string='Maximum',
        default=100,
        help='Upper bound of the random integer range (inclusive).',
    )

    # ── Password sub-options ─────────────────────────────────────────── #

    rand_password_type = fields.Selection(
        selection=[
            ('human_readable',          'Human Readable (words + numbers)'),
            ('letters_only',            'Random — Letters Only'),
            ('letters_numbers',         'Random — Letters & Numbers'),
            ('letters_numbers_symbols', 'Random — Letters, Numbers & Symbols'),
        ],
        string='Password Format',
        default='human_readable',
        help=(
            'Human Readable: memorable word + number combinations separated '
            'by hyphens (e.g. tiger-frost-42-ocean).\n\n'
            'Letters Only: cryptographically random alphabetic characters.\n\n'
            'Letters & Numbers: alphanumeric characters.\n\n'
            'Letters, Numbers & Symbols: full character set including '
            'punctuation symbols.'
        ),
    )
    rand_password_length = fields.Integer(
        string='Character Length',
        default=16,
        help=(
            'Total character length of the generated password.\n'
            'For Human Readable mode the result may be slightly shorter or '
            'longer depending on word lengths; it is trimmed to this length.'
        ),
    )

    # ------------------------------------------------------------------ #
    # Trigger sub-workflow fields                                          #
    # ------------------------------------------------------------------ #

    sub_workflow_id = fields.Many2one(
        'wf.automation',
        string='Sub-Workflow',
        ondelete='set null',
    )
    sub_workflow_record_type = fields.Selection(
        selection=[
            ('trigger', 'Same Trigger Record'),
            ('relation', 'Related Record (field)'),
        ],
        string='Run On',
        default='trigger',
    )
    sub_workflow_record_field_id = fields.Many2one(
        'ir.model.fields',
        string='Sub-Workflow Record Field',
        domain="[('model_id', '=', workflow_id.model_id)]",
    )

    # ------------------------------------------------------------------ #
    # Variable storage                                                     #
    # ------------------------------------------------------------------ #

    store_result_var = fields.Char(
        string='Store Result As',
        help='Variable name under which the step result is stored for use in later steps.',
    )

    # ------------------------------------------------------------------ #
    # API Call step fields                                                 #
    # ------------------------------------------------------------------ #

    api_service_platform_id = fields.Many2one(
        'wf.service.platform',
        string='Service / Platform',
        ondelete='set null',
        help=(
            'Authentication configuration to use for this API call.\n'
            'The platform\'s Base URL is prepended to the URL Path below.'
        ),
    )

    # Mirrors the selected platform's Base URL (readonly display only)
    api_base_url = fields.Char(
        string='Base URL',
        related='api_service_platform_id.base_url',
        readonly=True,
    )

    api_url_slug = fields.Char(
        string='URL Path',
        help=(
            'Relative path appended to the platform\'s Base URL.\n'
            'Supports {{expression}} templates.\n'
            'Example: /orders/{{record.id}}/complete'
        ),
    )

    api_method = fields.Selection(
        selection=[
            ('GET',    'GET'),
            ('POST',   'POST'),
            ('PUT',    'PUT'),
            ('PATCH',  'PATCH'),
            ('DELETE', 'DELETE'),
        ],
        string='HTTP Method',
        default='POST',
    )

    api_query_param_ids = fields.One2many(
        'wf.step.api.query.param',
        'step_id',
        string='Query Parameters',
        help=(
            'URL query-string parameters appended to the request URL as '
            '?key=value&key2=value2.  Applies to all HTTP methods.  '
            'Values support {{expression}} templates.'
        ),
    )

    api_header_ids = fields.One2many(
        'wf.step.api.header',
        'step_id',
        string='Custom Headers',
        help=(
            'Additional HTTP headers sent with the API request.  '
            'These are merged on top of the default '
            'Content-Type / Accept / Authorization headers.  '
            'Header values support {{expression}} templates.'
        ),
    )

    api_body_type = fields.Selection(
        selection=[
            ('key_value', 'Key / Value Pairs'),
            ('json',      'JSON Body'),
        ],
        string='Body Type',
        default='key_value',
        help=(
            'Key / Value Pairs: build the JSON body from the table below.\n'
            'JSON Body: write the JSON directly; {{expression}} placeholders are resolved.'
        ),
    )

    api_body_param_ids = fields.One2many(
        'wf.step.api.body.param',
        'step_id',
        string='Body Parameters',
    )

    api_body_json = fields.Text(
        string='JSON Body',
        help=(
            'Raw JSON template for the request body.\n'
            'Supports {{expression}} placeholders — each placeholder is evaluated\n'
            'and its string representation is substituted into the template before\n'
            'the result is parsed as JSON.\n\n'
            'Example:\n'
            '  {"order_id": {{record.id}}, "status": "{{record.state}}"}'
        ),
    )

    api_response_key_path = fields.Char(
        string='Response Key Path',
        help=(
            'Optional dot-separated path to extract a specific value from the\n'
            'JSON response before storing it in the result variable.\n\n'
            'Examples:\n'
            '  data.id          — extracts response["data"]["id"]\n'
            '  result.token     — extracts response["result"]["token"]\n\n'
            'Leave blank to store the full parsed response dict.'
        ),
    )

    api_timeout = fields.Integer(
        string='Timeout (s)',
        default=30,
        help='Maximum time in seconds to wait for a response before timing out.',
    )

    # ------------------------------------------------------------------ #
    # Canvas actions                                                       #
    # ------------------------------------------------------------------ #

    def action_duplicate(self, offset_x=30, offset_y=30):
        """Create a copy of this step without any connections and return its ID.

        Connections are excluded via ``copy=False`` on the connection one2many
        fields, so the duplicated step starts with a completely clean slate.

        The new step is placed ``offset_x`` / ``offset_y`` pixels to the
        bottom-right of the original on the canvas.  Returns the new step's
        integer ID (explicit return avoids JSON-RPC serialisation ambiguity).
        """
        self.ensure_one()
        new_step = self.copy(default={
            'canvas_x': self.canvas_x + offset_x,
            'canvas_y': self.canvas_y + offset_y,
            'name': f'{self.name} (copy)',
        })
        return new_step.id

    # ------------------------------------------------------------------ #
    # Execution                                                            #
    # ------------------------------------------------------------------ #

    def _execute(self, record, run_context):
        """Execute this step, returning a signal string.

        Returns:
            'continue' — step completed normally, proceed to next step.
            'skip'     — condition was not met, step was skipped.
            'stop'     — workflow should halt.
            'error'    — step raised an exception (already logged).
        """
        self.ensure_one()
        step_sudo = self.sudo()
        exec_log = run_context.get('execution_log')
        step_log = None

        # Create step log entry
        if exec_log and exec_log.id:
            step_log = self.env['wf.execution.log.step'].sudo().create({
                'execution_log_id': exec_log.id,
                'step_id': step_sudo.id,
                'step_name': step_sudo.name,
                'step_type': step_sudo.step_type,
                'sequence': step_sudo.sequence,
                'started_at': fields.Datetime.now(),
                'state': 'success',
            })

        start_ts = _time.time()
        signal = 'continue'
        result_summary = False
        error_message = False

        try:
            # ---- condition check ----
            if not self._check_condition(record, run_context):
                if step_sudo.on_condition_fail == 'stop_workflow':
                    signal = 'stop'
                else:
                    signal = 'skip'
                if step_log:
                    step_log.write({
                        'state': 'skipped' if signal == 'skip' else 'stopped',
                        'result_summary': 'Condition not met',
                    })
                return signal

            stype = step_sudo.step_type

            # ---- dispatch by type ----
            if stype == 'stop_workflow':
                signal = 'stop'
                result_summary = 'Workflow stopped by step'

            elif stype == 'conditional_branch':
                signal = step_sudo._exec_conditional_branch(record, run_context)
                result_summary = (
                    'Branch: condition met — following connections'
                    if signal == 'continue'
                    else 'Branch: condition not met — path blocked'
                )

            elif stype == 'python_code':
                result = step_sudo._exec_python_code(record, run_context)
                result_summary = repr(result)[:200] if result is not None else 'None'
                if step_sudo.store_result_var or step_sudo.python_result_var:
                    var_name = step_sudo.store_result_var or step_sudo.python_result_var
                    run_context['variables'][var_name] = result

            elif stype == 'api_call':
                result, api_status = step_sudo._exec_api_call(record, run_context)
                result_summary = 'API call completed (HTTP %s)' % api_status if api_status else 'API call completed'
                if step_sudo.store_result_var:
                    run_context['variables'][step_sudo.store_result_var] = result

            elif stype == 'random_generator':
                result = step_sudo._exec_random_generator(record, run_context)
                result_summary = 'Generated: %s' % str(result)[:120]
                if step_sudo.store_result_var:
                    run_context['variables'][step_sudo.store_result_var] = result

            elif stype == 'generate_report':
                attachments = step_sudo._exec_generate_report(record, run_context)
                result_summary = 'Generated %d report(s)' % len(attachments)
                # Store attachment ids in run_context for downstream steps
                if 'generated_report_attachments' not in run_context:
                    run_context['generated_report_attachments'] = []
                run_context['generated_report_attachments'].extend(attachments)
                if step_sudo.store_result_var:
                    run_context['variables'][step_sudo.store_result_var] = attachments

            elif stype in ('create_record', 'update_record', 'delete_record',
                           'add_activity', 'post_message', 'send_notification',
                           'send_email', 'trigger_workflow'):

                if stype == 'create_record':
                    new_records = step_sudo._exec_create_record(record, run_context)
                    result_summary = 'Created %d record(s)' % (len(new_records) if new_records else 0)
                    if step_sudo.store_result_var and new_records:
                        run_context['variables'][step_sudo.store_result_var] = new_records

                elif stype == 'update_record':
                    target_records = step_sudo._resolve_target_records(record, run_context)
                    step_sudo._exec_update_record(target_records, record, run_context)
                    result_summary = 'Updated %d record(s)' % len(target_records)

                elif stype == 'delete_record':
                    target_records = step_sudo._resolve_target_records(record, run_context)
                    count = len(target_records)
                    step_sudo._exec_delete_record(target_records, record, run_context)
                    result_summary = 'Deleted %d record(s)' % count

                elif stype == 'add_activity':
                    target_records = step_sudo._resolve_target_records(record, run_context)
                    step_sudo._exec_add_activity(target_records, record, run_context)
                    result_summary = 'Activity added to %d record(s)' % len(target_records)

                elif stype == 'post_message':
                    target_records = step_sudo._resolve_target_records(record, run_context)
                    step_sudo._exec_post_message(target_records, record, run_context)
                    result_summary = 'Message posted to %d record(s)' % len(target_records)

                elif stype == 'send_notification':
                    step_sudo._exec_send_notification(record, run_context)
                    result_summary = 'Bus notification sent'

                elif stype == 'send_email':
                    target_records = step_sudo._resolve_target_records(record, run_context)
                    step_sudo._exec_send_email(target_records, record, run_context)
                    if (step_sudo.email_type == 'inline'
                            and step_sudo.email_to_type == 'specific_users'):
                        n_users = len(step_sudo.email_to_user_ids.filtered('email'))
                        result_summary = 'Email sent to %d specific user(s)' % n_users
                    else:
                        result_summary = 'Email sent for %d record(s)' % len(target_records)

                elif stype == 'trigger_workflow':
                    step_sudo._exec_trigger_workflow(record, run_context)
                    result_summary = 'Sub-workflow triggered'

        except Exception as exc:
            signal = 'error'
            error_message = traceback.format_exc()
            _rec_name = record._name if record is not None else '(modelless)'
            _rec_id = record.id if record is not None else 0
            _logger.exception(
                "wf.step '%s' (ID %d) — error during execution on %s #%s",
                step_sudo.name,
                step_sudo.id,
                _rec_name,
                _rec_id,
            )

        # Update step log
        if step_log:
            duration_ms = int((_time.time() - start_ts) * 1000)
            state_map = {
                'continue': 'success',
                'skip': 'skipped',
                'stop': 'stopped',
                'blocked': 'stopped',   # conditional_branch: condition not met
                'error': 'error',
            }
            step_log.write({
                'ended_at': fields.Datetime.now(),
                'duration_ms': duration_ms,
                'state': state_map.get(signal, 'success'),
                'result_summary': result_summary,
                'error_message': error_message,
                'stored_variable_name': step_sudo.store_result_var or step_sudo.python_result_var or False,
            })

        return signal

    def _execute_modelless(self, run_context):
        """Execute this step in a modelless scheduled workflow (no trigger record).

        Delegates to ``_execute`` with ``record=None``.  Steps that require a
        record (e.g. post_message, update_record) will log a warning and skip
        gracefully rather than raising.
        """
        self.ensure_one()
        return self._execute(None, run_context)

    # ------------------------------------------------------------------ #
    # Condition helpers                                                    #
    # ------------------------------------------------------------------ #

    def _check_condition(self, record, run_context):
        """Return True if the step's condition is satisfied (or condition_type=='none').

        When *record* is None (modelless scheduled workflow), domain conditions
        are skipped and Python conditions are still evaluated without a record.
        """
        self.ensure_one()
        ctype = self.condition_type
        if ctype == 'none' or not ctype:
            return True

        eval_ctx = self._get_eval_context(record, run_context)

        if ctype == 'domain':
            if record is None:
                _logger.warning(
                    "wf.step '%s' — domain condition skipped in modelless workflow", self.name
                )
                return True
            try:
                domain = safe_eval.safe_eval(self.condition_domain or '[]', eval_ctx)
                return bool(record.sudo().filtered_domain(domain))
            except Exception:
                _logger.exception("wf.step '%s' — error evaluating condition domain", self.name)
                return False

        if ctype == 'python':
            try:
                result = safe_eval.safe_eval(self.condition_python or 'False', eval_ctx)
                return bool(result)
            except Exception:
                _logger.exception("wf.step '%s' — error evaluating condition python", self.name)
                return False

        return True

    # ------------------------------------------------------------------ #
    # Target record resolution                                             #
    # ------------------------------------------------------------------ #

    def _resolve_target_records(self, record, run_context):
        """Return the target recordset for this step based on target_record_type.

        *record* may be None for modelless scheduled workflows.  In that case
        only ``domain`` target type can produce records; ``trigger`` and
        ``relation`` types return an empty list (no trigger record to work from).
        """
        self.ensure_one()
        rtype = self.target_record_type or 'trigger'

        # Modelless execution: no trigger record available.
        if record is None:
            if rtype == 'domain':
                if not self.target_model_id:
                    return []
                Model = self.env.get(self.target_model_id.model)
                if Model is None:
                    return []
                eval_ctx = self._get_eval_context(None, run_context)
                try:
                    domain = safe_eval.safe_eval(self.target_domain or '[]', eval_ctx)
                    return Model.search(domain)
                except Exception:
                    _logger.exception(
                        "wf.step '%s' — error evaluating target domain (modelless)", self.name,
                    )
                    return Model.browse()
            # trigger / relation — nothing to resolve without a record
            return []

        if rtype == 'trigger':
            return record

        if rtype == 'relation':
            if not self.target_relation_field_id:
                return record.browse()
            field_name = self.target_relation_field_id.name
            try:
                related = record[field_name]
                if isinstance(related, models.BaseModel):
                    return related
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error resolving relation field '%s'",
                    self.name, field_name,
                )
            return record.browse()

        if rtype == 'domain':
            if not self.target_model_id:
                return record.browse()
            Model = self.env.get(self.target_model_id.model)
            if Model is None:
                return record.browse()
            eval_ctx = self._get_eval_context(record, run_context)
            try:
                domain = safe_eval.safe_eval(self.target_domain or '[]', eval_ctx)
                return Model.search(domain)
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error evaluating target domain", self.name,
                )
                return Model.browse()

        return record

    # ------------------------------------------------------------------ #
    # Step-type executors                                                  #
    # ------------------------------------------------------------------ #

    def _exec_create_record(self, record, run_context):
        """Create one new record in create_model_id with the configured field mappings."""
        self.ensure_one()
        if not self.create_model_id:
            _logger.warning("wf.step '%s' — create_model_id not set", self.name)
            return self.env['res.lang'].browse()  # empty recordset

        Model = self.env.get(self.create_model_id.model)
        if Model is None:
            _logger.warning(
                "wf.step '%s' — model '%s' not found",
                self.name, self.create_model_id.model,
            )
            return self.env['res.lang'].browse()

        vals = {}
        for mapping in self.field_mapping_ids:
            try:
                vals[mapping.field_id.name] = mapping.resolve_value(record, run_context)
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error resolving mapping for field '%s'",
                    self.name, mapping.field_id.name,
                )

        # Link back to trigger record
        if self.create_link_field_id:
            vals[self.create_link_field_id.name] = record.id

        try:
            return Model.create(vals)
        except Exception:
            _logger.exception("wf.step '%s' — error creating record in '%s'", self.name, Model._name)
            raise

    def _exec_update_record(self, target_records, record, run_context):
        """Write field mappings onto target_records."""
        self.ensure_one()
        if not target_records:
            return

        vals = {}
        for mapping in self.field_mapping_ids:
            try:
                vals[mapping.field_id.name] = mapping.resolve_value(record, run_context)
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error resolving mapping for field '%s'",
                    self.name, mapping.field_id.name,
                )

        if vals:
            try:
                target_records.write(vals)
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error writing to target records", self.name,
                )
                raise

    def _exec_delete_record(self, target_records, record, run_context):
        """Unlink target_records."""
        self.ensure_one()
        if target_records:
            try:
                target_records.unlink()
            except Exception:
                _logger.exception("wf.step '%s' — error deleting records", self.name)
                raise

    def _exec_generate_report(self, record, run_context):
        """Generate all configured reports and return list of attachment info dicts."""
        self.ensure_one()
        import base64
        generated = []
        for report in self.generate_report_ids:
            try:
                fname, data, mime = report.generate_report_bytes()
                att_vals = {
                    'name': fname,
                    'datas': base64.b64encode(data).decode(),
                    'mimetype': mime,
                }
                if record is not None and self.generate_report_attach_to_record:
                    att_vals['res_model'] = record._name
                    att_vals['res_id'] = record.id
                att = self.env['ir.attachment'].sudo().create(att_vals)
                generated.append({
                    'report_id': report.id,
                    'report_name': report.name,
                    'attachment_id': att.id,
                    'filename': fname,
                })
                _logger.info(
                    "wf.step '%s' — generated report '%s' → attachment #%d",
                    self.name, report.name, att.id,
                )
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error generating report '%s'",
                    self.name, report.name,
                )
        return generated

    def _get_preceding_report_names(self, run_context):
        """Return list of report names generated by any preceding Generate Report step."""
        attachments = run_context.get('generated_report_attachments', [])
        return [att['report_name'] for att in attachments if att.get('report_name')]

    def _exec_add_activity(self, target_records, record, run_context):
        """Schedule an activity on each target record."""
        self.ensure_one()
        if not target_records:
            return

        import datetime as dt
        eval_ctx = self._get_eval_context(record, run_context)

        deadline_date = (
            dt.date.today() + dt.timedelta(days=self.activity_deadline_days or 1)
        )

        # Resolve user
        user_id = self.env.uid
        utype = self.activity_user_type or 'current_user'
        if utype == 'specific_user' and self.activity_user_id:
            user_id = self.activity_user_id.id
        elif utype == 'record_user' and self.activity_user_field_id:
            fname = self.activity_user_field_id.name
            try:
                field_user = record[fname]
                if field_user:
                    user_id = field_user.id if hasattr(field_user, 'id') else int(field_user)
            except Exception:
                _logger.warning(
                    "wf.step '%s' — could not resolve user from field '%s'", self.name, fname,
                )

        summary = self._render_template(self.activity_summary or '', eval_ctx)
        note = self._render_template(self.activity_note or '', eval_ctx)

        for trec in target_records:
            if hasattr(trec, 'activity_schedule'):
                try:
                    trec.activity_schedule(
                        activity_type_id=self.activity_type_id.id,
                        summary=summary,
                        note=note,
                        date_deadline=deadline_date,
                        user_id=user_id,
                    )
                except Exception:
                    _logger.exception(
                        "wf.step '%s' — error scheduling activity on %s #%d",
                        self.name, trec._name, trec.id,
                    )

    def _exec_post_message(self, target_records, record, run_context):
        """Post a chatter message on each target record."""
        self.ensure_one()
        if not target_records:
            return

        from markupsafe import Markup
        eval_ctx = self._get_eval_context(record, run_context)
        # _render_template returns a plain str; re-wrap as Markup so Odoo's
        # mail system treats the content as trusted HTML instead of escaping it.
        body = Markup(self._render_template(self.message_body or '', eval_ctx))

        # Append report names if configured
        if self.include_report_names:
            report_names = self._get_preceding_report_names(run_context)
            if report_names:
                body = body + Markup('<br/><b>Generated Reports:</b> ') + Markup(', '.join(report_names))
        subtype_xmlid = (
            'mail.mt_note' if self.message_post_method == 'note'
            else 'mail.mt_comment'
        )
        subtype = self.env.ref(subtype_xmlid, raise_if_not_found=False)

        for trec in target_records:
            if hasattr(trec, 'message_post'):
                try:
                    kwargs = {'body': body}
                    if subtype:
                        kwargs['subtype_id'] = subtype.id
                    trec.message_post(**kwargs)
                except Exception:
                    _logger.exception(
                        "wf.step '%s' — error posting message on %s #%d",
                        self.name, trec._name, trec.id,
                    )

    def _exec_send_notification(self, record, run_context):
        """Send a bus (web push) notification to configured users."""
        self.ensure_one()
        eval_ctx = self._get_eval_context(record, run_context)
        message = self._render_template(self.notification_message or '', eval_ctx)
        level = self.notification_level or 'info'

        # Append report names if configured
        if self.include_report_names:
            report_names = self._get_preceding_report_names(run_context)
            if report_names:
                message = '%s | Reports: %s' % (message, ', '.join(report_names))

        # Determine users to notify
        if self.notification_target == 'specific_users':
            target_users = self.notification_user_ids
        else:
            target_users = self.env.user

        if not target_users:
            return

        payload = {
            'title':   _('Workflow Notification'),
            'message': message,
            'type':    level,
            'sticky':  False,
        }

        try:
            # res.users inherits bus.listener.mixin — _bus_send routes through
            # the correct Odoo 19 channel format automatically.
            for user in target_users:
                user._bus_send('simple_notification', payload)
        except Exception:
            _logger.exception("wf.step '%s' — error sending bus notification", self.name)

    def _exec_send_email(self, target_records, record, run_context):
        """Send an email using a template or inline body."""
        self.ensure_one()
        # specific_users inline mode sends to a fixed recipient list — it does
        # not iterate over target_records, so an empty recordset is fine.
        needs_target_records = (
            self.email_type == 'template'
            or self.email_to_type != 'specific_users'
        )
        if needs_target_records and not target_records:
            return

        eval_ctx = self._get_eval_context(record, run_context)

        # Build report attachments (ir.attachment ids) from Generate Report steps
        attachment_ids = []
        # Track attachments generated on-the-fly here (not by a preceding Generate
        # Report step) so we can pin them to the mail.message after creation.
        # Without pinning, they are orphaned (no res_model/res_id) and may not
        # appear as "unrestricted" in the mails UI for non-superuser viewers.
        on_the_fly_attachment_ids = []
        if self.email_attach_report_ids:
            existing_attachments = run_context.get('generated_report_attachments', [])
            # Filter to only the reports configured on this step
            selected_report_ids = set(self.email_attach_report_ids.ids)
            attachment_ids = [
                att['attachment_id'] for att in existing_attachments
                if att.get('report_id') in selected_report_ids
            ]
            # Generate on-the-fly for any selected reports not yet generated
            already_generated_report_ids = {att.get('report_id') for att in existing_attachments}
            for report in self.email_attach_report_ids:
                if report.id not in already_generated_report_ids:
                    try:
                        fname, data, mime = report.generate_report_bytes()
                        # Do NOT set res_model/res_id here — we'll pin the
                        # attachment to the mail.message after creation.
                        # Setting a business model here would cause Odoo to
                        # convert the attachment to a download link when the
                        # email exceeds the server size limit, and would crash
                        # entirely when record is None (modelless workflows).
                        att = self.env['ir.attachment'].sudo().create({
                            'name': fname,
                            'datas': __import__('base64').b64encode(data).decode(),
                            'mimetype': mime,
                        })
                        attachment_ids.append(att.id)
                        on_the_fly_attachment_ids.append(att.id)
                    except Exception:
                        _logger.exception(
                            "wf.step '%s' — error generating on-the-fly report '%s'",
                            self.name, report.name,
                        )

        if self.email_type == 'template' and self.email_template_id:
            for trec in target_records:
                try:
                    mail_id = self.email_template_id.send_mail(trec.id, force_send=False)
                    if attachment_ids:
                        mail = self.env['mail.mail'].browse(mail_id)
                        mail.write({'attachment_ids': [(4, aid) for aid in attachment_ids]})
                        # Pin on-the-fly attachments to this mail.message
                        if on_the_fly_attachment_ids:
                            self.env['ir.attachment'].sudo().browse(on_the_fly_attachment_ids).write({
                                'res_model': 'mail.message',
                                'res_id': mail.mail_message_id.id,
                            })
                    self.env['mail.mail'].browse(mail_id).send()
                except Exception:
                    _logger.exception(
                        "wf.step '%s' — error sending template email for %s #%d",
                        self.name, trec._name, trec.id,
                    )
        else:
            # Inline email
            subject = self._render_template(self.email_subject or '', eval_ctx)
            body_html = self._render_template(self.email_body or '', eval_ctx)

            # Append report names to body if configured
            if self.include_report_names:
                report_names = self._get_preceding_report_names(run_context)
                if report_names:
                    body_html += '<br/><b>Generated Reports:</b> ' + ', '.join(report_names)

            if self.email_to_type == 'specific_users':
                # Send one email addressed to all selected users
                recipients = self.email_to_user_ids.filtered('email')
                if not recipients:
                    _logger.warning(
                        "wf.step '%s' — no recipient email addresses found on selected users; skipping",
                        self.name,
                    )
                    return
                email_to = ','.join(recipients.mapped('email'))
                try:
                    mail_vals = {
                        'subject': subject,
                        'body_html': body_html,
                        'email_to': email_to,
                    }
                    if attachment_ids:
                        mail_vals['attachment_ids'] = [(4, aid) for aid in attachment_ids]
                    mail = self.env['mail.mail'].create(mail_vals)
                    # Pin any on-the-fly attachments to this mail.message so they
                    # show as "unrestricted" in the mails UI and are not orphaned.
                    if on_the_fly_attachment_ids:
                        self.env['ir.attachment'].sudo().browse(on_the_fly_attachment_ids).write({
                            'res_model': 'mail.message',
                            'res_id': mail.mail_message_id.id,
                        })
                    mail.send()
                except Exception:
                    _logger.exception(
                        "wf.step '%s' — error sending inline email to specific users '%s'",
                        self.name, email_to,
                    )
            else:
                # Resolve recipient from a field on each target record
                for trec in target_records:
                    email_to = False
                    if self.email_to_field_id:
                        try:
                            email_to = trec[self.email_to_field_id.name]
                            if hasattr(email_to, 'email'):
                                email_to = email_to.email
                            elif hasattr(email_to, 'mapped'):
                                email_to = ','.join(email_to.mapped('email'))
                        except Exception:
                            _logger.warning(
                                "wf.step '%s' — could not resolve email_to from field", self.name,
                            )

                    if not email_to:
                        _logger.warning(
                            "wf.step '%s' — no recipient email address for %s #%d; skipping",
                            self.name, trec._name, trec.id,
                        )
                        continue

                    try:
                        mail_vals = {
                            'subject': subject,
                            'body_html': body_html,
                            'email_to': email_to,
                        }
                        if attachment_ids:
                            mail_vals['attachment_ids'] = [(4, aid) for aid in attachment_ids]
                        mail = self.env['mail.mail'].create(mail_vals)
                        # Pin on-the-fly attachments to this mail.message.
                        # Each mail.mail gets its own message so we update them per
                        # iteration; pre-generated (Generate Report step) attachments
                        # are already pinned to the trigger record and need no update.
                        if on_the_fly_attachment_ids:
                            self.env['ir.attachment'].sudo().browse(on_the_fly_attachment_ids).write({
                                'res_model': 'mail.message',
                                'res_id': mail.mail_message_id.id,
                            })
                        mail.send()
                    except Exception:
                        _logger.exception(
                            "wf.step '%s' — error sending inline email to '%s'",
                            self.name, email_to,
                        )

    def _exec_python_code(self, record, run_context):
        """Execute arbitrary Python code and return the value of 'result'."""
        self.ensure_one()
        if not self.python_code:
            return None

        eval_ctx = self._get_eval_context(record, run_context)
        eval_ctx['result'] = None  # default

        try:
            safe_eval.safe_eval(
                self.python_code,
                eval_ctx,
                mode='exec',
            )
            return eval_ctx.get('result')
        except Exception:
            _logger.exception("wf.step '%s' — error executing python_code", self.name)
            raise

    def _exec_api_call(self, record, run_context):
        """Execute an outbound HTTP API call for this step.

        Flow
        ----
        1. Authenticate via the linked :class:`wf.service.platform` using
           :meth:`~wf.service.platform._get_token` (reuses cached token when
           still valid).
        2. Build the full URL from ``platform.base_url + api_url_slug``
           (``api_url_slug`` supports ``{{expression}}`` templates).
        3. Build the request headers — default Content-Type / Accept, then
           Bearer Authorization from the token, then custom header rows
           (``api_header_ids``), all with template resolution.
        4. Build the request body:
           * ``key_value`` mode — assemble body dict from ``api_body_param_ids``
             rows (static, record field, variable, or expression values).
           * ``json`` mode — render ``api_body_json`` as a template string,
             then parse as JSON.
        5. Execute the HTTP request via the ``requests`` library.
        6. Log the full call (request + response) to ``wf.api.call.log``.
        7. Parse the JSON response; apply ``api_response_key_path`` extraction
           if set; return the result (stored by ``_execute`` into
           ``run_context['variables'][store_result_var]``).

        Returns
        -------
        dict
            The parsed JSON response body (or extracted sub-value when
            ``api_response_key_path`` is set).  An internal key
            ``_status_code`` carries the HTTP status code for the result
            summary — it is stripped before the value is stored in the
            workflow variable.

        Raises
        ------
        :class:`~odoo.exceptions.UserError`
            When the platform is not configured, the URL cannot be built,
            the HTTP request fails, or the response is not valid JSON.
        """
        from odoo.exceptions import UserError

        self.ensure_one()
        platform = self.api_service_platform_id

        if not platform:
            raise UserError(
                _('Workflow step "%s" — no Service / Platform selected for the API Call.')
                % self.name
            )

        # ---- 1. HTTP method ---------------------------------------------
        method = (self.api_method or 'POST').upper()

        # ---- 2. Authenticate / get token --------------------------------
        # Runs for ALL HTTP methods (GET, POST, PUT, PATCH, DELETE).
        # _get_token() reuses the cached last_token when still valid;
        # otherwise calls _authenticate() and writes a new cache entry.
        # Either way the token is injected into eval_ctx as {{api_token}}
        # so operators can reference it anywhere in this step's templates.
        platform_sudo = platform.sudo()
        platform_sudo.invalidate_recordset(['last_token', 'last_token_expiry'])
        cached_before = bool(platform_sudo.last_token)
        token = platform_sudo._get_token(
            call_name='%s — Auth' % self.name,
            caller_model=record._name if record is not None else '(none)',
            caller_res_id=record.id if record is not None else False,
        )
        _logger.info(
            "wf.step '%s' — %s token for platform '%s': %s",
            self.name,
            'reused cached' if cached_before else 'obtained fresh',
            platform.name,
            ('%s…' % token[:8]) if token else '(empty — check platform credentials)',
        )
        if not token:
            _logger.warning(
                "wf.step '%s' — api_token is empty; {{api_token}} will render "
                "as blank in headers/params/body. Verify the platform's "
                "Response API Key and authentication endpoint.",
                self.name,
            )

        # ---- 3. Build eval context with api_token -----------------------
        # api_token (and its alias api_key) are injected first so they are
        # available in ALL template fields: URL slug, query params, headers,
        # and body.  Both names are accepted so operators can use whichever
        # feels natural:  {{api_token}}  or  {{api_key}}
        eval_ctx = self._get_eval_context(record, run_context)
        eval_ctx['api_token'] = token or ''
        eval_ctx['api_key']   = token or ''

        # ---- 4. Build URL -----------------------------------------------
        base_url = (platform.base_url or '').rstrip('/')
        if not base_url:
            raise UserError(
                _('Service / Platform "%s" has no Base URL configured.') % platform.name
            )
        raw_slug = self._render_template(self.api_url_slug or '', eval_ctx)
        slug = raw_slug.strip().lstrip('/')
        url = ('%s/%s' % (base_url, slug)) if slug else base_url

        # ---- 5. Build query parameters ----------------------------------
        # Resolved and passed as params= to requests (URL-encoded automatically).
        # Works for all HTTP methods — Postman Params tab behaviour.
        query_params = {}
        for param_row in self.api_query_param_ids.sorted('sequence'):
            resolved_val = self._render_template(param_row.value or '', eval_ctx)
            query_params[param_row.name] = resolved_val

        # ---- 6. Build headers -------------------------------------------
        headers = {
            'Content-Type': 'application/json',
            'Accept':       'application/json',
        }
        for header_row in self.api_header_ids.sorted('sequence'):
            resolved_val = self._render_template(header_row.value or '', eval_ctx)
            headers[header_row.name] = resolved_val

        # ---- 7. Build body (only for methods that carry one) ------------
        body = None
        logged_body = None

        if method not in ('GET', 'DELETE'):
            if self.api_body_type == 'json':
                raw_json = self._render_template(self.api_body_json or '', eval_ctx)
                if raw_json.strip():
                    try:
                        body = json.loads(raw_json)
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise UserError(
                            _('API Call step "%s" — invalid JSON body after template '
                              'rendering: %s') % (self.name, exc)
                        ) from exc
                    logged_body = body  # JSON body has no secrets
                else:
                    body = {}
                    logged_body = {}
            else:
                # Key / value pairs
                body = {}
                logged_body = {}
                for param in self.api_body_param_ids.sorted('sequence'):
                    try:
                        val = param.resolve_value(record, run_context)
                    except Exception:
                        _logger.exception(
                            "wf.step '%s' — error resolving body param '%s'",
                            self.name, param.key,
                        )
                        val = None
                    body[param.key] = val
                    logged_body[param.key] = val

        # ---- Append report names to body if configured ------------------
        if self.include_report_names and body is not None:
            report_names = self._get_preceding_report_names(run_context)
            if report_names:
                if isinstance(body, dict):
                    body['_generated_report_names'] = report_names
                    logged_body['_generated_report_names'] = report_names

        # ---- 5. Execute request -----------------------------------------
        _logger.info(
            "wf.step '%s' — %s %s (params: %s)", self.name, method, url,
            list(query_params.keys()) if query_params else 'none',
        )

        t_start = _time.time()
        response = None
        state = 'success'
        error_message = None
        dispatched_url = url  # updated to the actual URL-with-params after the call

        try:
            kwargs = dict(headers=headers, timeout=self.api_timeout or 30)
            if query_params:
                kwargs['params'] = query_params
            if method in ('POST', 'PUT', 'PATCH') and body is not None:
                kwargs['json'] = body
            response = requests.request(method, url, **kwargs)
            # response.request.url is the real URL as sent, including encoded params
            dispatched_url = response.request.url or url
            response.raise_for_status()
        except RequestException as exc:
            state = 'error'
            # Include the response body in the message so the API's actual
            # error detail is visible in the UserError and the server log.
            resp_preview = ''
            if response is not None and response.text:
                resp_preview = response.text[:2000]
            error_message = '%s\n\nResponse body:\n%s' % (exc, resp_preview) \
                if resp_preview else str(exc)
            _logger.error(
                "wf.step '%s' — API request to %s failed: %s\nResponse body: %s",
                self.name, dispatched_url, exc, resp_preview or '(none)',
            )

        duration_ms = int((_time.time() - t_start) * 1000)

        # ---- 6. Parse response ------------------------------------------
        raw_response = {}
        response_body_text = ''
        response_body_formatted = ''
        response_status = None
        response_headers_dict = {}

        if response is not None:
            response_status = response.status_code
            response_headers_dict = dict(response.headers)
            response_body_text = response.text or ''
            if response_body_text:
                try:
                    response_body_formatted = json.dumps(
                        json.loads(response_body_text), indent=2
                    )
                except (ValueError, TypeError):
                    response_body_formatted = response_body_text
            if state == 'success':
                try:
                    raw_response = response.json()
                except ValueError as exc:
                    state = 'error'
                    error_message = (
                        'API response is not valid JSON: %s' % exc
                    )

        # ---- 7. Write API call log entry --------------------------------
        self.env['wf.api.call.log']._create_log(
            name='%s — %s' % (self.name, method),
            endpoint=dispatched_url,  # full URL including encoded query params
            http_method=method,
            request_headers=json.dumps(
                _redact_api_headers(headers), indent=2
            ),
            request_body=(
                json.dumps(logged_body, indent=2) if logged_body is not None else None
            ),
            response_status_code=response_status,
            response_headers=(
                json.dumps(_redact_api_headers(response_headers_dict), indent=2)
                if response_headers_dict else None
            ),
            response_body=(response_body_formatted or response_body_text)[:65536],
            state=state,
            error_message=error_message,
            duration_ms=duration_ms,
            service_platform_id=platform.id,
            trigger_model=record._name if record is not None else '(none)',
            trigger_res_id=record.id if record is not None else False,
        )

        # ---- 8. Surface errors after logging ----------------------------
        if state == 'error':
            from odoo.exceptions import UserError as _UE
            raise _UE(
                _('API Call step "%s" failed: %s') % (self.name, error_message)
            )

        # ---- 9. Extract result ------------------------------------------
        result = raw_response
        key_path = (self.api_response_key_path or '').strip()
        if key_path:
            # If the top-level response is a single-item list, auto-unwrap it
            # so simple paths like "id" work without needing "0.id".
            # Multi-item lists still require an explicit index: "0.id".
            target = raw_response
            if isinstance(target, list) and len(target) == 1:
                target = target[0]
            extracted = _resolve_dot_path(target, key_path)
            if extracted is not None:
                result = extracted
            else:
                _logger.warning(
                    "wf.step '%s' — response key path '%s' not found in response "
                    "(type: %s%s). Storing full response. "
                    "Use dot-notation for nested keys (e.g. data.id) or integer "
                    "indices for lists (e.g. 0.id).",
                    self.name, key_path,
                    type(raw_response).__name__,
                    (', keys: %s' % list(raw_response.keys()))
                    if isinstance(raw_response, dict) else
                    (', length: %d' % len(raw_response))
                    if isinstance(raw_response, list) else '',
                )

        return result, response_status

    def _exec_conditional_branch(self, record, run_context):
        """Evaluate the branch condition and return 'continue' or 'blocked'.

        'continue'  — condition met; the graph engine will evaluate outgoing
                      connections and queue matching downstream steps.
        'blocked'   — condition not met; the graph engine will skip this
                      branch's connections WITHOUT clearing the global queue,
                      so parallel branches that already queued their steps
                      continue to execute normally.

        Note: ``branch_action`` previously controlled whether a failed condition
        halted the entire workflow ('stop') or continued ('continue').  That
        model was broken in multi-branch workflows because 'stop' cleared the
        queue for *all* branches, not just the failing one.  The correct way to
        abort an entire workflow on a failed condition is to connect this branch
        to a ``stop_workflow`` step via the appropriate connection condition.
        """
        self.ensure_one()
        eval_ctx = self._get_eval_context(record, run_context)
        condition_met = False

        if self.branch_condition_type == 'domain':
            try:
                domain = safe_eval.safe_eval(self.branch_condition_domain or '[]', eval_ctx)
                condition_met = bool(record.sudo().filtered_domain(domain))
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error evaluating branch domain", self.name,
                )
        else:
            try:
                condition_met = bool(
                    safe_eval.safe_eval(self.branch_condition_python or 'False', eval_ctx)
                )
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error evaluating branch python", self.name,
                )

        if not condition_met:
            _logger.debug(
                "wf.step '%s' (conditional_branch) — condition NOT met, path blocked",
                self.name,
            )
            return 'blocked'

        _logger.debug(
            "wf.step '%s' (conditional_branch) — condition met, following connections",
            self.name,
        )
        return 'continue'

    def _exec_random_generator(self, record, run_context):
        """Generate a random word, number, or password and return the result.

        Uses ``secrets`` for all generation so values are
        cryptographically strong (important for password mode).

        Returns:
            str  — for word / password generation
            int  — for number generation
        """
        self.ensure_one()
        gen_type = self.rand_generate_type or 'word'

        # ── Word ─────────────────────────────────────────────────────── #
        if gen_type == 'word':
            count = max(1, self.rand_word_count or 1)
            chosen = [secrets.choice(_WF_WORD_LIST) for _ in range(count)]
            separator = ' ' if self.rand_word_spaces else ''
            return separator.join(chosen)

        # ── Number ───────────────────────────────────────────────────── #
        elif gen_type == 'number':
            lo = int(self.rand_number_min or 1)
            hi = int(self.rand_number_max or 100)
            if lo > hi:
                lo, hi = hi, lo
            span = hi - lo + 1
            return lo + secrets.randbelow(span)

        # ── Password ─────────────────────────────────────────────────── #
        elif gen_type == 'password':
            length = max(4, self.rand_password_length or 16)
            pwd_type = self.rand_password_type or 'human_readable'

            if pwd_type == 'human_readable':
                # Build "word-number-word-number-…" and trim to length.
                parts = []
                total = 0
                while total < length:
                    word = secrets.choice(_WF_WORD_LIST)
                    parts.append(word)
                    total += len(word)
                    if total < length:
                        num = str(secrets.randbelow(100))
                        parts.append(num)
                        total += len(num)
                    if total < length:
                        parts.append('-')
                        total += 1
                raw = ''.join(parts)
                # Trim exactly to the requested length, but never cut mid-word
                # on a hyphen boundary if we can avoid it.
                return raw[:length]

            else:
                if pwd_type == 'letters_only':
                    alphabet = string.ascii_letters
                elif pwd_type == 'letters_numbers':
                    alphabet = string.ascii_letters + string.digits
                else:  # letters_numbers_symbols
                    # Use a printable-symbol subset that avoids whitespace,
                    # backslash, backtick and quotes (shell/UI unfriendly).
                    alphabet = (
                        string.ascii_letters
                        + string.digits
                        + '!@#$%^&*()-_=+[]{}|;:,.<>?'
                    )
                return ''.join(secrets.choice(alphabet) for _ in range(length))

        return ''

    def _exec_trigger_workflow(self, record, run_context):
        """Trigger a sub-workflow on the appropriate record(s)."""
        self.ensure_one()
        if not self.sub_workflow_id:
            _logger.warning("wf.step '%s' — sub_workflow_id not set", self.name)
            return

        target_records = record
        if self.sub_workflow_record_type == 'relation' and self.sub_workflow_record_field_id:
            fname = self.sub_workflow_record_field_id.name
            try:
                target_records = record[fname]
            except Exception:
                _logger.exception(
                    "wf.step '%s' — error resolving sub-workflow target record field", self.name,
                )
                return

        try:
            self.sub_workflow_id._process(target_records, 'manual')
        except Exception:
            _logger.exception(
                "wf.step '%s' — error triggering sub-workflow '%s'",
                self.name, self.sub_workflow_id.name,
            )
            raise

    # ------------------------------------------------------------------ #
    # Template rendering                                                   #
    # ------------------------------------------------------------------ #

    def _render_template(self, template_str, eval_ctx):
        """Render a string containing ``{{expression}}`` placeholders.

        Each ``{{expr}}`` block is replaced by the result of evaluating *expr*
        in *eval_ctx* via safe_eval.

        Args:
            template_str: The template string.
            eval_ctx: The evaluation context dict.

        Returns:
            The rendered string.
        """
        if not template_str or '{{' not in template_str:
            return template_str or ''

        def replacer(match):
            expr = match.group(1).strip()
            try:
                value = safe_eval.safe_eval(expr, eval_ctx)
                return str(value) if value is not None else ''
            except Exception:
                _logger.warning(
                    "wf.step '%s' — error rendering template expression '{{%s}}'",
                    self.name if self else '?', expr,
                )
                return ''

        return _TEMPLATE_RE.sub(replacer, template_str)

    # ------------------------------------------------------------------ #
    # Eval context                                                         #
    # ------------------------------------------------------------------ #

    def _get_eval_context(self, record, run_context):
        """Build the safe_eval context for this step.

        *record* may be None for modelless scheduled workflows; callers that
        use ``ctx['record']`` for domain filtering must guard for None.
        """
        ctx = {
            'datetime': safe_eval.datetime,
            'dateutil': safe_eval.dateutil,
            'time': safe_eval.time,
            'uid': self.env.uid,
            'user': self.env.user,
            'env': self.env,
            'record': record,   # may be None
            'model': record,    # may be None
            'step': self,
            'workflow': run_context.get('workflow') if run_context else None,
            'trigger_type': run_context.get('trigger_type') if run_context else None,
            'old_values': (run_context or {}).get('old_values', {}),
            'variables': (run_context or {}).get('variables', {}),
        }
        ctx.update((run_context or {}).get('variables', {}))
        return ctx
