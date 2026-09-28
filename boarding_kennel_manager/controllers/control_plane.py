"""The Control Plane: an installable (PWA) full-screen page per yard for the enclosure screens."""
import json
from datetime import datetime

from markupsafe import Markup

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.tools import file_open, format_datetime

BASE = '/kennel/control-plane'
KEEPER_GROUP = 'boarding_kennel_manager.group_kennel_keeper'


def _date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def _parse_date(text):
    """dd/mm/yyyy (as typed on the screen) -> date; empty -> False."""
    text = (text or '').strip()
    if not text:
        return False
    try:
        return datetime.strptime(text, '%d/%m/%Y').date()
    except ValueError:
        raise ValidationError(request.env._('"%s" is not a date. Use dd/mm/yyyy.', text))


class KennelControlPlane(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _yard(self, yard_id):
        """The yard, if the current user is a keeper who can see it."""
        if not request.env.user.has_group(KEEPER_GROUP):
            raise AccessError(request.env._('The Control Plane is for Boarding Kennel Manager keepers.'))
        yard = request.env['kennel.yard'].browse(yard_id).exists()
        if not yard:
            raise MissingError(request.env._('This yard no longer exists.'))
        yard.check_access('read')
        return yard

    def _current_lines(self, yard):
        """The stays of the animals checked in to this yard right now."""
        return request.env['kennel.booking.line'].search(
            [('yard_id', '=', yard.id), ('booking_id.state', '=', 'checked_in')], order='arrival_datetime')

    def _options(self, model, domain=None):
        return [{'id': rec.id, 'name': rec.display_name} for rec in request.env[model].search(domain or [])]

    def _when(self, value, company, dt_format='HH:mm'):
        return format_datetime(request.env, value, tz=company._kennel_tz().zone, dt_format=dt_format) if value else ''

    def _theme(self, company):
        return {
            'theme': company.kennel_cp_theme,
            'background': company.kennel_cp_background,
            'transparency': company.kennel_cp_image_transparency,
            'light': company.kennel_cp_colour_light or '#F5F5F5',
            'dark': company.kennel_cp_colour_dark or '#1E1E1E',
            'image_url': f'/web/image/res.company/{company.id}/kennel_cp_background_image'
                         if company.kennel_cp_background_image else '',
            'logo_url': f'/web/image/res.company/{company.id}/logo' if company.logo else '',
            'refresh_minutes': max(company.kennel_cp_refresh_minutes, 0),
        }

    def _data(self, yard):
        """Everything the screen shows, as plain values."""
        company = yard.company_id
        lines = self._current_lines(yard)
        # Make sure today's tasks exist (it's idempotent), then list today's and anything overdue.
        request.env['kennel.task']._generate_for_bookings(lines.booking_id)
        today = datetime.now(company._kennel_tz()).date()
        Task = request.env['kennel.task']
        todo = Task.search([('yard_id', '=', yard.id), ('state', '=', 'todo'), ('date', '<=', today),
                            ('booking_id.state', '=', 'checked_in')])
        done = Task.search([('yard_id', '=', yard.id), ('state', '=', 'done'), ('date', '=', today)],
                           order='done_datetime desc')
        type_labels = dict(Task._fields['task_type']._description_selection(request.env))

        def task_values(task):
            return {
                'id': task.id, 'type': task.task_type, 'type_label': type_labels.get(task.task_type),
                'name': task.name, 'resident': task.resident_id.name,
                'due': self._when(task.scheduled_datetime, company),
                'overdue': task.overdue, 'instructions': task.instructions or '',
                'done_at': self._when(task.done_datetime, company), 'done_by': task.done_by_id.name or '',
                'problem': task.problem,
                # What the completion form starts with.
                'quantity_given': task.quantity_given or '', 'dose_given': task.dose_given or '',
            }

        residents = []
        for line in lines:
            resident = line.resident_id
            residents.append({
                'id': resident.id,
                'line_id': line.id,
                'name': resident.name,
                'photo_url': f'/web/image/kennel.resident/{resident.id}/image_512' if resident.image_128 else '',
                'species': resident.species_id.name or '',
                'breed': resident.breed or '',
                'sex': ' '.join(filter(None, [resident.sex_id.name, '(desexed)' if resident.desexed else ''])),
                'age': resident.age or '',
                'colour': resident.colour or '',
                'microchip': resident.microchip or '',
                'customer': resident.partner_id.name,
                'booking': line.booking_id.name,
                'arrival': self._when(line.arrival_datetime, company, 'dd/MM/yyyy HH:mm'),
                'departure': self._when(line.departure_datetime, company, 'dd/MM/yyyy HH:mm'),
                'food': line._feed_description(),
                'feeding_instructions': line.feeding_instructions or '',
                'owner_supplied_food': line.owner_supplied_food,
                'medical': line.medical_notes or '',
                'behaviour': resident.behaviour_notes or '',
                'vaccinations_due': _date(resident.vaccination_expiry_date),
                'vaccination_expired': line.vaccination_expired,
                'medication': [f'{m.name} {m.dose or ""}'.strip() for m in line.booking_id.medication_ids
                               if m.resident_id == resident],
            })
        medications = lines.booking_id.medication_ids.filtered(lambda m: m.resident_id in lines.resident_id)
        return {
            'yard': {
                'id': yard.id, 'name': yard.name, 'code': yard.code or '',
                'type': yard.yard_type_id.name or '', 'company': company.name,
                'capacity': yard.capacity, 'features': yard.feature_ids.mapped('name'),
            },
            'today': today.strftime('%d/%m/%Y'),
            'residents': residents,
            'tasks': [task_values(task) for task in todo],
            'done': [task_values(task) for task in done],
            'options': {
                'residents': [{'id': r['id'], 'name': r['name']} for r in residents],
                'consumption': self._options('kennel.feed.consumption'),
                'outcome': self._options('kennel.dose.outcome'),
                'observation_type': self._options('kennel.observation.type'),
                'route': self._options('kennel.medication.route'),
                'frequency': self._options('kennel.frequency'),
                'medication': [{'id': m.id, 'name': m.display_name, 'dose': m.dose or ''} for m in medications],
            },
            'theme': self._theme(company),
        }

    def _line_for(self, yard, resident_id):
        line = self._current_lines(yard).filtered(lambda l: l.resident_id.id == int(resident_id or 0))
        if not line:
            raise ValidationError(request.env._('Pick an animal that is in this yard.'))
        return line[:1]

    def _photos(self, task, photos):
        """Attach photos taken on the screen ([{name, data (base64)}]) to a task."""
        attachments = request.env['ir.attachment']
        for photo in photos or []:
            if photo.get('data'):
                attachments |= request.env['ir.attachment'].create({
                    'name': photo.get('name') or 'photo.jpg', 'datas': photo['data'],
                    'res_model': 'kennel.task', 'res_id': task.id,
                })
        if attachments:
            task.photo_ids = [(4, attachment.id) for attachment in attachments]

    def _id(self, value):
        return int(value) if value else False

    def _complete(self, task, values):
        """Fill in a task from the screen's form and close it out."""
        vals = {'notes': values.get('notes') or False}
        if task.task_type == 'feed':
            vals.update(consumption_id=self._id(values.get('consumption_id')),
                        quantity_given=values.get('quantity_given') or False)
        elif task.task_type == 'medication':
            vals.update(outcome_id=self._id(values.get('outcome_id')), dose_given=values.get('dose_given') or False)
        else:
            vals.update(summary=values.get('summary') or False, concern=bool(values.get('concern')))
            if values.get('observation_type_id'):
                vals['observation_type_id'] = self._id(values['observation_type_id'])
        task.write(vals)
        self._photos(task, values.get('photos'))
        task.action_complete()

    def _save(self, env, yard, kind, values):
        if kind == 'task':
            task = env['kennel.task'].browse(int(values.get('task_id') or 0)).exists()
            if not task or task.yard_id != yard:
                raise ValidationError(env._('That task is not for this yard.'))
            self._complete(task, values)
        elif kind == 'care':
            line = self._line_for(yard, values.get('resident_id'))
            task_type = values.get('task_type') if values.get('task_type') in ('feed', 'observation') else 'feed'
            now = fields.Datetime.now()
            task = env['kennel.task'].create({
                'task_type': task_type, 'booking_id': line.booking_id.id, 'line_id': line.id,
                'date': datetime.now(yard.company_id._kennel_tz()).date(), 'scheduled_datetime': now,
            })
            self._complete(task, values)
        elif kind == 'observation':
            line = self._line_for(yard, values.get('resident_id'))
            env['kennel.observation'].create({
                'booking_id': line.booking_id.id, 'resident_id': line.resident_id.id,
                **({'type_id': self._id(values['observation_type_id'])} if values.get('observation_type_id') else {}),
                'summary': values.get('summary'), 'details': values.get('details') or False,
                'concern': bool(values.get('concern')),
            })
        elif kind == 'medication':
            line = self._line_for(yard, values.get('resident_id'))
            env['kennel.medication'].create({
                'booking_id': line.booking_id.id, 'resident_id': line.resident_id.id,
                'name': values.get('name'), 'dose': values.get('dose') or False,
                'route_id': self._id(values.get('route_id')), 'frequency_id': self._id(values.get('frequency_id')),
                'times': values.get('times') or False, 'instructions': values.get('instructions') or False,
                'start_date': _parse_date(values.get('start_date')), 'end_date': _parse_date(values.get('end_date')),
            })
        elif kind == 'dose':
            medication = env['kennel.medication'].browse(int(values.get('medication_id') or 0)).exists()
            if not medication or medication.booking_id not in self._current_lines(yard).booking_id:
                raise ValidationError(env._('Pick a medication for an animal in this yard.'))
            env['kennel.medication.administration'].create({
                'booking_id': medication.booking_id.id, 'medication_id': medication.id,
                'dose_given': values.get('dose_given') or False,
                'outcome_id': self._id(values.get('outcome_id')), 'notes': values.get('notes') or False,
            })
        else:
            raise ValidationError(env._('Unknown form.'))

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route(f'{BASE}/<int:yard_id>', type='http', auth='user')
    def page(self, yard_id, **kw):
        try:
            yard = self._yard(yard_id)
        except (AccessError, MissingError) as error:
            return request.make_response(str(error), status=403, headers=[('Content-Type', 'text/plain; charset=utf-8')])
        data = self._data(yard)
        return request.render('boarding_kennel_manager.control_plane_page', {
            'yard': yard,
            'data_json': Markup(json.dumps(data).replace('</', '<\\/')),
            'theme': data['theme'],
            'version': request.env['ir.module.module'].sudo().search(
                [('name', '=', 'boarding_kennel_manager')]).latest_version or '1',
        })

    @http.route(f'{BASE}/<int:yard_id>/manifest.webmanifest', type='http', auth='user')
    def manifest(self, yard_id, **kw):
        yard = self._yard(yard_id)
        dark = yard.company_id.kennel_cp_theme == 'dark'
        manifest = {
            'name': f'{yard.name} - Control Plane',
            'short_name': yard.code or yard.name,
            'start_url': f'{BASE}/{yard.id}',
            'scope': f'{BASE}/',
            'display': 'fullscreen',
            'orientation': 'landscape',
            'background_color': yard.company_id.kennel_cp_colour_dark if dark else yard.company_id.kennel_cp_colour_light,
            'theme_color': '#2e7d6e',
            'icons': [
                {'src': '/boarding_kennel_manager/static/src/control_plane/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
                {'src': '/boarding_kennel_manager/static/src/control_plane/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
            ],
        }
        return request.make_response(json.dumps(manifest), headers=[('Content-Type', 'application/manifest+json')])

    @http.route(f'{BASE}/sw.js', type='http', auth='public')
    def service_worker(self, **kw):
        """Served from the Control Plane path so it can control every yard's screen."""
        with file_open('boarding_kennel_manager/static/src/control_plane/service_worker.js') as f:
            body = f.read()
        return request.make_response(body, headers=[
            ('Content-Type', 'text/javascript; charset=utf-8'), ('Cache-Control', 'no-cache')])

    # ------------------------------------------------------------------
    # Data and actions (JSON-RPC)
    # ------------------------------------------------------------------

    @http.route(f'{BASE}/<int:yard_id>/data', type='jsonrpc', auth='user')
    def data(self, yard_id, **kw):
        return self._data(self._yard(yard_id))

    @http.route(f'{BASE}/<int:yard_id>/submit', type='jsonrpc', auth='user')
    def submit(self, yard_id, kind, values=None, **kw):
        """Save a form filled in on the screen. Returns fresh data, or {'error': message}."""
        yard = self._yard(yard_id)
        values = values or {}
        env = request.env
        try:
            with env.cr.savepoint():
                self._save(env, yard, kind, values)
        except (UserError, ValidationError, AccessError) as error:
            return {'error': str(error.args[0] if error.args else error)}
        return {'data': self._data(yard)}
