from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ZooAnimal(models.Model):
    _name = 'zoo.animal'
    _description = 'Animal'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name, reference'

    reference = fields.Char(
        required=True, copy=False, readonly=True, index=True, default=lambda self: self.env._('New'),
    )
    name = fields.Char(required=True, tracking=True)
    class_id = fields.Many2one(
        'zoo.animal.class', string='Class', index=True,
        compute='_compute_class_id', store=True, readonly=False,
        help='Pick a class to narrow the species list.',
    )
    species_id = fields.Many2one(
        'zoo.species', required=True, tracking=True, index=True,
        domain="[('class_id', '=', class_id)] if class_id else []",
    )
    sex = fields.Selection(
        [('male', 'Male'), ('female', 'Female'), ('unknown', 'Unknown')],
        default='unknown', required=True, tracking=True,
    )
    identifier = fields.Char(string='Tag / Microchip', tracking=True, help='Ear tag, ring, microchip or other identifier.')
    date_of_birth = fields.Date(tracking=True)
    birth_date_estimated = fields.Boolean(string='Estimated Birth Date')
    age = fields.Char(compute='_compute_age')

    enclosure_id = fields.Many2one('zoo.enclosure', tracking=True, index=True)
    move_ids = fields.One2many('zoo.animal.move', 'animal_id', string='Moves')

    sire_id = fields.Many2one(
        'zoo.animal', string='Sire', index=True,
        domain="[('sex', '=', 'male'), ('id', '!=', id), ('id', '!=', dam_id)]",
    )
    dam_id = fields.Many2one(
        'zoo.animal', string='Dam', index=True,
        domain="[('sex', '=', 'female'), ('id', '!=', id), ('id', '!=', sire_id)]",
    )
    sired_ids = fields.One2many('zoo.animal', 'sire_id', string='Offspring (as Sire)')
    mothered_ids = fields.One2many('zoo.animal', 'dam_id', string='Offspring (as Dam)')

    origin_id = fields.Many2one('zoo.animal.origin', string='Origin', tracking=True)
    seller_id = fields.Many2one('res.partner', string='Seller', tracking=True, index=True,
                                help='Who the animal was bought or acquired from.')
    origin_details = fields.Char(help='Where the animal came from, e.g. the sending zoo or rescue organisation.')
    arrival_date = fields.Date(default=fields.Date.context_today, tracking=True)

    state = fields.Selection(
        [
            ('present', 'In Collection'),
            ('transferred', 'Transferred Out'),
            ('deceased', 'Deceased'),
        ],
        string='Status', default='present', required=True, tracking=True, index=True,
    )
    departure_date = fields.Date(tracking=True)
    departure_reason = fields.Text()

    diet_id = fields.Many2one('zoo.diet', tracking=True)
    diet_line_ids = fields.One2many(related='diet_id.line_ids')

    weight_ids = fields.One2many('zoo.animal.weight', 'animal_id', string='Weights')
    latest_weight = fields.Float(string='Latest Weight (kg)', compute='_compute_latest_weight', digits=(16, 3))
    latest_weight_date = fields.Date(compute='_compute_latest_weight')

    health_record_ids = fields.One2many('zoo.health.record', 'animal_id', string='Health Records')
    health_record_count = fields.Integer(compute='_compute_health_record_count')
    open_health_record_count = fields.Integer(compute='_compute_health_record_count')

    feeding_ids = fields.Many2many(
        'zoo.feeding', 'zoo_animal_feeding_rel', 'animal_id', 'feeding_id', string='Feedings',
    )
    note_ids = fields.One2many('zoo.animal.note', 'animal_id', string='Notes')
    feeding_count = fields.Integer(compute='_compute_counts')
    move_count = fields.Integer(compute='_compute_counts')
    note_count = fields.Integer(compute='_compute_counts')
    active = fields.Boolean(default=True)

    _reference_uniq = models.Constraint('UNIQUE (reference)', 'Animal reference must be unique.')

    @api.depends('date_of_birth', 'state', 'departure_date')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for animal in self:
            if not animal.date_of_birth:
                animal.age = False
                continue
            end = animal.departure_date if animal.state == 'deceased' and animal.departure_date else today
            delta = relativedelta(end, animal.date_of_birth)
            if delta.years:
                age = self.env._('%(years)s y %(months)s m', years=delta.years, months=delta.months)
            elif delta.months:
                age = self.env._('%(months)s m', months=delta.months)
            else:
                age = self.env._('%(days)s d', days=max(delta.days, 0))
            animal.age = ('~' if animal.birth_date_estimated else '') + age

    @api.depends('weight_ids.weight', 'weight_ids.date')
    def _compute_latest_weight(self):
        for animal in self:
            latest = animal.weight_ids.sorted(lambda w: (w.date, w.id))[-1:]
            animal.latest_weight = latest.weight
            animal.latest_weight_date = latest.date

    @api.depends('health_record_ids.state')
    def _compute_health_record_count(self):
        for animal in self:
            animal.health_record_count = len(animal.health_record_ids)
            animal.open_health_record_count = len(animal.health_record_ids.filtered(lambda r: r.state == 'open'))

    @api.depends('feeding_ids', 'move_ids', 'note_ids')
    def _compute_counts(self):
        for animal in self:
            animal.feeding_count = len(animal.feeding_ids)
            animal.move_count = len(animal.move_ids)
            animal.note_count = len(animal.note_ids)

    @api.depends('name', 'reference')
    def _compute_display_name(self):
        for animal in self:
            animal.display_name = f'{animal.name} ({animal.reference})' if animal.reference else animal.name

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ('ilike', '=') and isinstance(value, str) and value:
            return ['|', '|', ('name', operator, value), ('reference', operator, value), ('identifier', operator, value)]
        return super()._search_display_name(operator, value)

    @api.constrains('sire_id', 'dam_id')
    def _check_parents(self):
        for animal in self:
            if animal in (animal.sire_id | animal.dam_id):
                raise ValidationError(self.env._('%s cannot be its own sire or dam.', animal.name))
            if animal.sire_id and animal.sire_id == animal.dam_id:
                raise ValidationError(self.env._('%s: the sire and dam must be different animals.', animal.name))
            # Walk up the family tree: the animal mustn't turn up among its own ancestors
            # (e.g. one of its offspring picked as its sire).
            ancestors = seen = animal.sire_id | animal.dam_id
            while ancestors:
                if animal in ancestors:
                    raise ValidationError(self.env._(
                        '%s cannot be its own ancestor: check its sire and dam.', animal.name))
                ancestors = (ancestors.sire_id | ancestors.dam_id) - seen
                seen |= ancestors

    @api.constrains('date_of_birth', 'arrival_date', 'departure_date')
    def _check_dates(self):
        for animal in self:
            if animal.date_of_birth and animal.departure_date and animal.departure_date < animal.date_of_birth:
                raise ValidationError(self.env._('%s: departure date cannot be before the date of birth.', animal.name))

    @api.depends('species_id.class_id')
    def _compute_class_id(self):
        for animal in self:
            animal.class_id = animal.species_id.class_id or animal.class_id

    @api.onchange('class_id')
    def _onchange_class_id(self):
        if self.species_id and self.class_id and self.species_id.class_id != self.class_id:
            self.species_id = False

    @api.onchange('species_id')
    def _onchange_species_id(self):
        if self.species_id.default_diet_id and not self.diet_id:
            self.diet_id = self.species_id.default_diet_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', self.env._('New')) == self.env._('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('zoo.animal') or self.env._('New')
            if not vals.get('diet_id') and vals.get('species_id'):
                vals['diet_id'] = self.env['zoo.species'].browse(vals['species_id']).default_diet_id.id
        animals = super().create(vals_list)
        moves = [
            {'animal_id': animal.id, 'to_enclosure_id': animal.enclosure_id.id, 'reason': self.env._('Arrival')}
            for animal in animals if animal.enclosure_id
        ]
        if moves:
            self.env['zoo.animal.move'].create(moves)
        return animals

    def write(self, vals):
        moves = []
        if 'enclosure_id' in vals:
            reason = self.env.context.get('zoo_move_reason')
            for animal in self:
                if animal.enclosure_id.id != (vals['enclosure_id'] or False):
                    moves.append({
                        'animal_id': animal.id,
                        'from_enclosure_id': animal.enclosure_id.id,
                        'to_enclosure_id': vals['enclosure_id'] or False,
                        'reason': reason,
                    })
        if vals.get('state') in ('transferred', 'deceased') and 'departure_date' not in vals:
            vals['departure_date'] = fields.Date.context_today(self)
        res = super().write(vals)
        if moves:
            self.env['zoo.animal.move'].create(moves)
        return res

    def action_view_health_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Health Records'),
            'res_model': 'zoo.health.record',
            'view_mode': 'list,form',
            'domain': [('animal_id', '=', self.id)],
            'context': {'default_animal_id': self.id},
        }

    def action_view_weights(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Weights'),
            'res_model': 'zoo.animal.weight',
            'view_mode': 'list,graph,form',
            'domain': [('animal_id', '=', self.id)],
            'context': {'default_animal_id': self.id},
        }

    def action_view_feedings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Feedings'),
            'res_model': 'zoo.feeding',
            'view_mode': 'list,form',
            'domain': [('animal_ids', 'in', self.id)],
            'context': {'default_enclosure_id': self.enclosure_id.id},
        }

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Moves'),
            'res_model': 'zoo.animal.move',
            'view_mode': 'list,form',
            'domain': [('animal_id', '=', self.id)],
        }

    def action_view_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Notes'),
            'res_model': 'zoo.animal.note',
            'view_mode': 'list,form',
            'domain': [('animal_id', '=', self.id)],
            'context': {'default_animal_id': self.id},
        }

    def action_view_family_tree(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'zoo_manager.family_tree',
            'name': self.env._('Family Tree'),
            'context': {'active_id': self.id},
        }

    def _family_tree_node(self):
        return {
            'id': self.id,
            'name': self.name,
            'reference': self.reference,
            'sex': self.sex,
            'species': self.species_id.name,
            'born': self.date_of_birth.strftime('%d/%m/%Y') if self.date_of_birth else False,
            'born_estimated': self.birth_date_estimated,
            'state': self.state,
            'state_label': dict(self._fields['state']._description_selection(self.env)).get(self.state),
            'has_image': bool(self.image_128),
        }

    def _family_tree_ancestors(self, depth, path):
        """Pedigree: this animal with its sire and dam, recursively."""
        node = self._family_tree_node()
        node['branches'] = []
        if depth > 0:
            for parent, role in ((self.sire_id, self.env._('Sire')), (self.dam_id, self.env._('Dam'))):
                if parent and parent.id not in path:
                    branch = parent._family_tree_ancestors(depth - 1, path | {parent.id})
                    branch['role'] = role
                    node['branches'].append(branch)
        return node

    def _family_tree_descendants(self, depth, path):
        """Offspring, recursively; each child shows its other parent."""
        node = self._family_tree_node()
        node['branches'] = []
        if depth > 0:
            children = (self.sired_ids | self.mothered_ids).sorted(
                lambda a: (a.date_of_birth or fields.Date.today(), a.name or '', a.id))
            for child in children:
                if child.id in path:
                    continue
                branch = child._family_tree_descendants(depth - 1, path | {child.id})
                other = child.dam_id if child.sire_id == self else child.sire_id
                branch['role'] = self.env._('with %s', other.name) if other else False
                node['branches'].append(branch)
        return node

    def get_family_tree(self, ancestor_generations=10, descendant_generations=10):
        """Family tree for the family tree view: up to 10 generations of
        parents and 10 of offspring. Archived animals are included so the
        lineage stays complete."""
        self.ensure_one()
        animal = self.with_context(active_test=False)
        ancestor_generations = max(0, min(int(ancestor_generations), 10))
        descendant_generations = max(0, min(int(descendant_generations), 10))
        return {
            'animal': animal._family_tree_node(),
            'ancestors': animal._family_tree_ancestors(ancestor_generations, {animal.id}),
            'descendants': animal._family_tree_descendants(descendant_generations, {animal.id}),
        }
