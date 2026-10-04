from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HelpBulkUpdateWizard(models.TransientModel):
    _name = 'help.bulk.update.wizard'
    _description = 'Bulk Update Help Articles'

    # ── Selection ──────────────────────────────────────────────────────────────

    article_ids = fields.Many2many(
        'help.article', string='Articles',
    )
    article_count = fields.Integer(
        'Article Count', compute='_compute_article_count',
    )

    # ── Category ───────────────────────────────────────────────────────────────

    update_category = fields.Boolean('Update Category')
    category_id = fields.Many2one(
        'help.category', string='Category', ondelete='set null',
    )

    # ── Audience ───────────────────────────────────────────────────────────────

    update_audience = fields.Boolean('Update Audience')
    audience = fields.Selection([
        ('internal', 'Internal Only'),
        ('external', 'External / Public'),
        ('both', 'Both (Internal & External)'),
    ], string='Audience')

    # ── Featured ───────────────────────────────────────────────────────────────

    update_is_featured = fields.Boolean('Update Featured')
    is_featured = fields.Boolean('Featured')

    # ── Author ─────────────────────────────────────────────────────────────────

    update_author = fields.Boolean('Update Author')
    author_id = fields.Many2one('res.users', string='Author')

    # ── Scheduled Publish ──────────────────────────────────────────────────────

    update_publish_date = fields.Boolean('Update Scheduled Publish')
    publish_date_action = fields.Selection([
        ('set', 'Set date'),
        ('clear', 'Clear scheduled date'),
    ], string='Publish Action', default='set')
    publish_date = fields.Datetime(
        'Publish At',
        default=lambda self: fields.Datetime.now() + timedelta(hours=1),
    )

    # ── Computes ───────────────────────────────────────────────────────────────

    @api.depends('article_ids')
    def _compute_article_count(self):
        for rec in self:
            rec.article_count = len(rec.article_ids)

    # ── Constraints ────────────────────────────────────────────────────────────

    @api.constrains('update_publish_date', 'publish_date_action', 'publish_date')
    def _check_publish_date(self):
        for rec in self:
            if (
                rec.update_publish_date
                and rec.publish_date_action == 'set'
                and rec.publish_date
                and rec.publish_date <= fields.Datetime.now()
            ):
                raise ValidationError(_('The scheduled publish date must be in the future.'))

    # ── Apply ──────────────────────────────────────────────────────────────────

    def action_apply(self):
        self.ensure_one()

        if not self.article_ids:
            raise UserError(_('No articles selected.'))

        # Build only the fields the user ticked
        updates = {}

        if self.update_category:
            updates['category_id'] = self.category_id.id or False

        if self.update_audience:
            if not self.audience:
                raise UserError(_('Please select an Audience value.'))
            updates['audience'] = self.audience

        if self.update_is_featured:
            updates['is_featured'] = self.is_featured

        if self.update_author:
            updates['author_id'] = self.author_id.id or False

        if self.update_publish_date:
            if self.publish_date_action == 'clear':
                updates['publish_date'] = False
            else:
                if not self.publish_date:
                    raise UserError(_('Please set a Scheduled Publish date.'))
                updates['publish_date'] = self.publish_date

        if not updates:
            raise UserError(_('Tick at least one field to update.'))

        self.article_ids.write(updates)
        return {'type': 'ir.actions.act_window_close'}
