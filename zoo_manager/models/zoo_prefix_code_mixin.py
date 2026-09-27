import re
from itertools import combinations, product
from string import ascii_uppercase

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ZooPrefixCodeMixin(models.AbstractModel):
    """A short, unique, upper-case letter code, suggested from the record's name."""

    _name = 'zoo.prefix.code.mixin'
    _description = 'Prefix Code'

    # Number of letters in the code; set by each model using the mixin.
    _prefix_code_length = 3

    prefix_code = fields.Char(required=True, copy=False, index=True)

    @api.constrains('prefix_code')
    def _check_prefix_code(self):
        pattern = re.compile(r'^[A-Z]{%d}$' % self._prefix_code_length)
        for record in self:
            if not pattern.match(record.prefix_code or ''):
                raise ValidationError(self.env._(
                    'Prefix Code must be exactly %(length)s letters (A-Z), not "%(code)s".',
                    length=self._prefix_code_length, code=record.prefix_code,
                ))

    @api.onchange('name')
    def _onchange_name_suggest_prefix_code(self):
        if self.name and not self.prefix_code:
            self.prefix_code = self._suggest_prefix_code(self.name)

    @api.model
    def _prefix_code_candidates(self, name):
        """Yield codes built from the name, best first: initials of the words
        (Eastern Grey Kangaroo -> EGK), the initials plus the start of the last
        word (Red Panda -> RPA), the start of the first word, then the first
        letter with any later letters in order. Falls back to every code
        starting with the first letter, then every code at all."""
        length = self._prefix_code_length
        words = re.findall(r'[A-Z]+', (name or '').upper())
        letters = ''.join(words)
        if len(words) >= length:
            yield ''.join(word[0] for word in words[:length])
        if len(words) > 1:
            yield (''.join(word[0] for word in words[:-1]) + words[-1])[:length]
        if words:
            yield words[0][:length]
        if letters:
            for rest in combinations(letters[1:], length - 1):
                yield letters[0] + ''.join(rest)
            for rest in product(ascii_uppercase, repeat=length - 1):
                yield letters[0] + ''.join(rest)
        for code in product(ascii_uppercase, repeat=length):
            yield ''.join(code)

    @api.model
    def _suggest_prefix_code(self, name, exclude=()):
        """First candidate code for `name` not used by any record (archived
        included) and not in `exclude`."""
        taken = set(self.with_context(active_test=False).search([]).mapped('prefix_code'))
        taken.update(exclude)
        for code in self._prefix_code_candidates(name):
            if len(code) == self._prefix_code_length and code not in taken:
                return code
        return False

    @api.model_create_multi
    def create(self, vals_list):
        assigned = set()
        for vals in vals_list:
            if vals.get('prefix_code'):
                vals['prefix_code'] = vals['prefix_code'].strip().upper()
            elif vals.get('name'):
                vals['prefix_code'] = self._suggest_prefix_code(vals['name'], exclude=assigned)
            if vals.get('prefix_code'):
                assigned.add(vals['prefix_code'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('prefix_code'):
            vals['prefix_code'] = vals['prefix_code'].strip().upper()
        return super().write(vals)
