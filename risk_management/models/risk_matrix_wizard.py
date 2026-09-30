from markupsafe import Markup

from odoo import api, fields, models

CELL_STYLE = (
    'border:1px solid #ccc;padding:8px;text-align:center;vertical-align:middle;'
    'min-width:110px;'
)
HEADER_STYLE = 'border:1px solid #ccc;padding:8px;text-align:center;font-weight:bold;background-color:#f5f5f5;'


class RiskMatrixWizard(models.TransientModel):
    _name = 'risk.matrix.wizard'
    _description = 'Risk Matrix'

    matrix_html = fields.Html(compute='_compute_matrix_html', sanitize=False)

    @api.depends()
    def _compute_matrix_html(self):
        likelihoods = self.env['risk.likelihood'].search([], order='sequence, value desc')
        consequences = self.env['risk.consequence'].search([], order='sequence, value')
        scores = self.env['risk.score'].search([])
        score_map = {(score.likelihood_id.id, score.consequence_id.id): score for score in scores}

        header_cells = Markup('').join(
            Markup('<th style="{style}">{name}</th>').format(style=HEADER_STYLE, name=consequence.name)
            for consequence in consequences
        )
        rows = []
        for likelihood in likelihoods:
            cells = [Markup('<th style="{style}text-align:left;">{name}</th>').format(
                style=HEADER_STYLE, name=likelihood.name,
            )]
            for consequence in consequences:
                score = score_map.get((likelihood.id, consequence.id))
                if score:
                    cell_style = '%sbackground-color:%s;color:%s;font-weight:bold;' % (
                        CELL_STYLE, score.bg_color, score.text_color,
                    )
                    cells.append(Markup(
                        '<td style="{style}">{label}<div style="font-size:0.85em;font-weight:normal;">'
                        '{score}</div></td>'
                    ).format(style=cell_style, label=score.label, score=score.score))
                else:
                    cells.append(Markup('<td style="{style}background-color:#fafafa;"></td>').format(style=CELL_STYLE))
            rows.append(Markup('<tr>{}</tr>').format(Markup('').join(cells)))

        table = Markup(
            '<table style="border-collapse:collapse;width:100%;">'
            '<caption style="caption-side:top;text-align:left;font-weight:bold;padding-bottom:8px;">'
            'Consequence &#8594;<br/>Likelihood &#8595;</caption>'
            '<thead><tr><th style="{header_style}"></th>{header}</tr></thead>'
            '<tbody>{rows}</tbody></table>'
        ).format(header_style=HEADER_STYLE, header=header_cells, rows=Markup('').join(rows))

        for wizard in self:
            wizard.matrix_html = table
