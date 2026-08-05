# -*- coding: utf-8 -*-
from odoo import fields, models


class DgStorageLocation(models.Model):
    _name = 'dg.storage.location'
    _description = 'Storage Location'
    _order = 'sequence, name'

    name = fields.Char('Location Name', required=True)
    building = fields.Char('Building / Site')
    description = fields.Text('Description')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DgPpeType(models.Model):
    _name = 'dg.ppe.type'
    _description = 'PPE Type'
    _order = 'sequence, name'

    name = fields.Char('PPE Type', required=True, translate=True)
    description = fields.Text('Description / Standard', translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DgStorageClass(models.Model):
    """AS 3833 Dangerous Goods storage classes."""
    _name = 'dg.storage.class'
    _description = 'DG Storage Class (AS 3833)'
    _order = 'sequence, code'

    name = fields.Char('Storage Class Name', required=True)
    code = fields.Char('Code', size=10)
    description = fields.Text('Description')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for rec in self:
            label = f'[{rec.code}] {rec.name}' if rec.code else rec.name
            result.append((rec.id, label))
        return result


class DgAdgClass(models.Model):
    """Australian Dangerous Goods Code transport classes (ADG Code 7.8)."""
    _name = 'dg.adg.class'
    _description = 'ADG Transport Class'
    _order = 'sequence, code'

    name = fields.Char('ADG Class Name', required=True)
    code = fields.Char('Class / Division', size=10, required=True,
                       help='e.g. 1.1, 2.1, 3, 4.1, 5.1, 6.1, 8, 9')
    description = fields.Text('Description')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f'Class {rec.code} — {rec.name}'))
        return result


class DgBuilding(models.Model):
    _name = 'dg.building'
    _description = 'Building / Site'
    _order = 'sequence, name'

    name = fields.Char('Building / Site Name', required=True)
    address = fields.Text('Address')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DgAsbestosForm(models.Model):
    _name = 'dg.asbestos.form'
    _description = 'Asbestos Form / Material Type'
    _order = 'sequence, name'

    name = fields.Char('Form Name', required=True, translate=True)
    description = fields.Text('Description', translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DgControlMeasure(models.Model):
    _name = 'dg.control.measure'
    _description = 'Control Measure'
    _order = 'sequence, name'

    name = fields.Char('Control Measure', required=True, translate=True)
    description = fields.Text('Description', translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class DgChemicalStage(models.Model):
    """Configurable pipeline stages for the Chemical Register status bar."""
    _name = 'dg.chemical.stage'
    _description = 'Chemical Register Stage'
    _order = 'sequence, id'

    name = fields.Char('Stage Name', required=True, translate=True)
    code = fields.Char(
        'Internal Code', size=32, readonly=True,
        help='Internal identifier used by system logic. '
             'Set automatically for standard stages — do not change.')
    sequence = fields.Integer('Sequence', default=10)
    fold = fields.Boolean(
        'Closed Stage',
        help='Closed stages are folded in the status bar and excluded from '
             'expiry notifications (use for Discontinued and Archived stages).')
    description = fields.Char('Description')


class DgAsbestosRemover(models.Model):
    """Licensed asbestos removalists / contractors."""
    _name = 'dg.asbestos.remover'
    _description = 'Asbestos Removalist / Contractor'
    _order = 'name'

    name = fields.Char('Company / Contractor Name', required=True)
    licence_number = fields.Char('Licence Number')
    licence_class = fields.Selection([
        ('a', 'Class A — Friable Asbestos'),
        ('b', 'Class B — Non-Friable Asbestos'),
    ], string='Licence Class')
    licence_expiry = fields.Date('Licence Expiry')
    contact_name = fields.Char('Contact Person')
    phone = fields.Char('Phone')
    email = fields.Char('Email')
    active = fields.Boolean(default=True)
