This module patches
[`account_statement_import_qif`](https://github.com/OCA/bank-statement-import/tree/19.0/account_statement_import_qif)
(from [OCA/bank-statement-import](https://github.com/OCA/bank-statement-import),
branch `19.0`) to fix ambiguous QIF date parsing.

That module parses QIF transaction dates with
`dateutil.parser.parse(..., fuzzy=True)`, which defaults to **month-first**
(US) ordering whenever a date is ambiguous. QIF files exported by non-US
banks (e.g. Australian banks) commonly use **day-first** ordering, so a date
like `08/07/26` (8 July) was silently misread as August 7th. See
[OCA/bank-statement-import#982](https://github.com/OCA/bank-statement-import/issues/982).

This module depends on `account_statement_import_qif` and overrides its
`_parse_file` method to parse dates day-first for any company whose country
isn't the United States, leaving month-first parsing for US companies
unchanged. It does not modify or replace `account_statement_import_qif`
itself, so it can be installed alongside the upstream OCA module (from
whichever git source provides it) without any file or module-name conflict.
