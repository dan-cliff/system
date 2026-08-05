# Copyright 2015 Odoo S. A.
# Copyright 2015 Laurent Mignon <laurent.mignon@acsone.eu>
# Copyright 2015 Ronald Portier <rportier@therp.nl>
# Copyright 2016-2017 Tecnativa - Pedro M. Baeza
# Copyright 2024 Tecnativa - Víctor Martínez
# Copyright 2026 Bendigo Scouts
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from datetime import date

from odoo.tests.common import TransactionCase
from odoo.tools.misc import file_path


class TestQifFile(TransactionCase):
    """Tests for import bank statement qif file format
    (account.bank.statement.import)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.statement_import_model = cls.env["account.statement.import"]
        cls.statement_line_model = cls.env["account.bank.statement.line"]
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test bank journal",
                "code": "TEST",
                "type": "bank",
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                # Different case for trying insensitive case search
                "name": "EPIC Technologies",
            }
        )

    def _import_qif_data(self, qif_data, filename="test.qif"):
        qif_file = base64.b64encode(qif_data.encode())
        wizard = self.statement_import_model.with_context(
            journal_id=self.journal.id
        ).create({"statement_file": qif_file, "statement_filename": filename})
        wizard.import_file_button()
        return wizard

    def test_qif_file_import(self):
        qif_file_path = file_path(
            "account_statement_import_qif_dayfirst_fix/tests/test_qif.qif"
        )
        qif_file = base64.b64encode(open(qif_file_path, "rb").read())
        wizard = self.statement_import_model.with_context(
            journal_id=self.journal.id
        ).create({"statement_file": qif_file, "statement_filename": "test_qif.qif"})
        wizard.import_file_button()
        statement = self.statement_line_model.search(
            [("payment_ref", "=", "YOUR LOCAL SUPERMARKET")],
            limit=1,
        ).statement_id
        self.assertAlmostEqual(statement.balance_end_real, -1896.09, 2)
        line = self.statement_line_model.search(
            [("payment_ref", "=", "Epic Technologies")],
            limit=1,
        )
        self.assertEqual(line.partner_id, self.partner)

    def test_qif_file_import_dayfirst_for_non_us_company(self):
        """Regression test for OCA/bank-statement-import#982: a company
        outside the US (e.g. Australia) must have ambiguous QIF dates
        parsed day-first, not month-first.
        """
        self.env.company.country_id = self.env.ref("base.au").id
        qif_data = (
            "!Type:Bank\n"
            "D08/07/2026\n"
            "T360.00\n"
            "PAU Dayfirst Payee\n"
            "^\n"
        )
        self._import_qif_data(qif_data, filename="test_au.qif")
        line = self.statement_line_model.search(
            [("payment_ref", "=", "AU Dayfirst Payee")], limit=1
        )
        self.assertEqual(line.date, date(2026, 7, 8))

    def test_qif_file_import_monthfirst_for_us_company(self):
        """The historical month-first behaviour is preserved for US
        companies, so this fix does not change existing US imports.
        """
        self.env.company.country_id = self.env.ref("base.us").id
        qif_data = (
            "!Type:Bank\n"
            "D08/07/2026\n"
            "T360.00\n"
            "PUS Monthfirst Payee\n"
            "^\n"
        )
        self._import_qif_data(qif_data, filename="test_us.qif")
        line = self.statement_line_model.search(
            [("payment_ref", "=", "US Monthfirst Payee")], limit=1
        )
        self.assertEqual(line.date, date(2026, 8, 7))
