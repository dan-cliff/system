# Copyright 2026 Bendigo Scouts
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
#
# Patches account_statement_import_qif's date parsing. Portions of
# _parse_file below are copied from that module (Copyright 2015 Odoo S.A.,
# Laurent Mignon, Ronald Portier; Copyright 2016-2017 Tecnativa - Pedro M.
# Baeza; License AGPL-3.0 or later) with only the date-parsing line changed.

import dateutil.parser

from odoo import models
from odoo.exceptions import UserError


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    def _get_qif_dayfirst(self):
        """Whether ambiguous QIF dates (e.g. ``08/07/26``) should be read
        day-first rather than month-first.

        QIF has no way to encode which convention was used to produce the
        file: it simply reflects the exporting bank's locale. The only
        common locale that puts the month first is the United States, so
        default to day-first for every other company country and fall back
        to month-first (the historical behaviour of account_statement_import_qif)
        when no country is configured.
        """
        country_code = self.env.company.country_id.code
        return bool(country_code) and country_code != "US"

    def _parse_file(self, data_file):
        if not self._check_qif(data_file):
            return super()._parse_file(data_file)
        try:
            file_data = data_file.decode()
            if "\r" in file_data:
                data_list = file_data.split("\r")
            else:
                data_list = file_data.split("\n")
            header = data_list[0].strip()
            header = header.split(":")[1]
        except Exception as e:
            raise UserError(self.env._("Could not decipher the QIF file.")) from e
        transactions = []
        vals_line = {}
        total = 0
        dayfirst = self._get_qif_dayfirst()
        if header in ("Bank", "CCard"):
            vals_bank_statement = {}
            for line in data_list:
                line = line.strip()
                if not line:
                    continue
                if line[0] == "D":  # date of transaction
                    vals_line["date"] = dateutil.parser.parse(
                        line[1:], fuzzy=True, dayfirst=dayfirst
                    ).date()
                elif line[0] == "T":  # Total amount
                    total += float(line[1:].replace(",", ""))
                    vals_line["amount"] = float(line[1:].replace(",", ""))
                elif line[0] == "N":  # Check number
                    vals_line["ref"] = line[1:]
                elif line[0] == "P":  # Payee
                    vals_line["payment_ref"] = (
                        "name" in vals_line
                        and line[1:] + ": " + vals_line["name"]
                        or line[1:]
                    )
                elif line[0] == "M":  # Memo
                    vals_line["payment_ref"] = (
                        "name" in vals_line
                        and vals_line["name"] + ": " + line[1:]
                        or line[1:]
                    )
                elif line[0] == "^" and vals_line:  # end of item
                    transactions.append(vals_line)
                    vals_line = {}
                elif line[0] == "\n":
                    transactions = []
                else:
                    pass
        else:
            raise UserError(
                self.env._(
                    "This file is either not a bank statement or is "
                    "not correctly formed."
                )
            )
        vals_bank_statement.update(
            {"balance_end_real": total, "transactions": transactions}
        )
        journal = self.env["account.journal"].browse(self.env.context.get("journal_id"))
        return journal.currency_id.name, None, [vals_bank_statement]
