# -*- coding: utf-8 -*-
"""Conditional display: when a question is shown on a checklist.

A question with Conditional Display is shown when all (or any) of its
conditions hold:

- answer rules on other questions of the template (checklist.question.condition),
  evaluated live on the form (static/src/checklist_checks) and here for the PDF;
- a Current User filter (a domain on res.users the user must match);
- a Checklist filter (a domain on checklist.checklist: company, organisation,
  asset, template, dates...).
"""
from datetime import datetime

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

# Technical: the evaluators below depend on these codes.
OPERATORS = [
    ('set', 'is answered'),
    ('not_set', 'is not answered'),
    ('eq', 'is equal to'),
    ('ne', 'is not equal to'),
    ('contains', 'contains'),
    ('gt', 'is greater than'),
    ('lt', 'is less than'),
    ('in', 'is any of'),
    ('not_in', 'is none of'),
]
SINGLE_OPTION_TYPES = ('buttons', 'select', 'radio', 'slider')
MULTI_OPTION_TYPES = ('multi_select', 'multi_checkbox')
TEXT_TYPES = ('text', 'text_area', 'phone', 'email', 'website')


class ChecklistQuestionCondition(models.Model):
    _name = 'checklist.question.condition'
    _description = 'Checklist Question Display Condition'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one(
        'checklist.question', string='Question', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    source_question_id = fields.Many2one(
        'checklist.question', string='When Question', required=True, ondelete='cascade',
        help='The answer this condition looks at.',
    )
    source_question_type = fields.Selection(related='source_question_id.question_type')
    operator = fields.Selection(OPERATORS, string='Condition', required=True, default='set')
    value = fields.Char(
        string='Value',
        help='Text, a number, a date (dd/mm/yyyy) or yes/no, depending on the question.',
    )
    option_ids = fields.Many2many(
        'checklist.question.option', 'checklist_condition_option_rel', 'condition_id', 'option_id',
        string='Options', domain="[('question_id', '=', source_question_id)]",
    )

    def _rule_vals(self):
        """The condition as copied onto checklist lines (JSON)."""
        return [{
            'question_id': condition.source_question_id.id,
            'question_type': condition.source_question_id.question_type,
            'operator': condition.operator,
            'value': condition.value or '',
            'option_ids': condition.option_ids.ids,
        } for condition in self]


def _is_answered(kind, answer):
    if kind in ('number', 'integer'):
        return bool(answer)
    if kind in MULTI_OPTION_TYPES or kind == 'many2many':
        return bool(answer)
    return answer not in (None, False, '', 0)


def _to_number(value):
    try:
        return float(str(value).replace(',', '').strip())
    except ValueError:
        return None


def _to_date(value):
    try:
        return datetime.strptime(str(value).strip(), '%d/%m/%Y').date()
    except ValueError:
        return None


def evaluate_rule(rule, answer):
    """Whether an answer (see checklist.line._condition_answer) meets a rule.

    Mirrored in static/src/checklist_checks/conditions.js for the form. Other
    types (records, files, images, locations) only test answered / not.
    """
    kind, operator, value = rule['question_type'], rule['operator'], rule.get('value') or ''
    options = set(rule.get('option_ids') or [])
    answered = _is_answered(kind, answer)
    if operator == 'set':
        return answered
    if operator == 'not_set':
        return not answered
    if kind in SINGLE_OPTION_TYPES or kind in MULTI_OPTION_TYPES:
        chosen = set(answer or []) if kind in MULTI_OPTION_TYPES else ({answer} if answer else set())
        if operator in ('in', 'eq'):
            return bool(chosen & options)
        if operator in ('not_in', 'ne'):
            return not (chosen & options)
        if operator == 'contains':
            return options <= chosen
        return False
    if kind == 'boolean':
        wanted = value.strip().lower() in ('1', 'true', 'yes', 'y')
        return (bool(answer) == wanted) if operator == 'eq' else (bool(answer) != wanted) if operator == 'ne' else False
    if kind in ('number', 'integer'):
        number = _to_number(value)
        if number is None:
            return False
        answer = answer or 0.0
        return {'eq': answer == number, 'ne': answer != number,
                'gt': answer > number, 'lt': answer < number}.get(operator, False)
    if kind in ('date', 'datetime'):
        wanted = _to_date(value)
        if wanted is None or not answer:
            return operator == 'ne' and not answer
        return {'eq': answer == wanted, 'ne': answer != wanted,
                'gt': answer > wanted, 'lt': answer < wanted}.get(operator, False)
    if kind in TEXT_TYPES:
        text, wanted = (answer or '').strip().lower(), value.strip().lower()
        return {'eq': text == wanted, 'ne': text != wanted,
                'contains': wanted in text}.get(operator, False)
    return False


def eval_domain(env, domain):
    """A filter (domain string from the filter builder) as a list."""
    if not domain or domain.strip() in ('', '[]'):
        return []
    return safe_eval(domain, {'uid': env.uid, 'user': env.user, 'context_today': fields.Date.context_today})


def combine(logic, results):
    results = [result for result in results if result is not None]
    if not results:
        return True
    return all(results) if logic == 'all' else any(results)
